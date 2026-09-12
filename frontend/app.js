"use strict";

const log = document.getElementById("log");
const statusEl = document.getElementById("status");
const composer = document.getElementById("composer");
const textInput = document.getElementById("text");
const urlInput = document.getElementById("url");
const ingestBtn = document.getElementById("ingest");
const urlList = document.getElementById("url-list");
const urlsRefreshBtn = document.getElementById("urls-refresh");
const urlsTitle = document.getElementById("urls-title");

let ws = null;
let fallbackBackend = null;

function localDevBackend() {
  if (location.port !== "8080") return null;
  return `${location.protocol}//${location.hostname}:8000`;
}

function backendOrigin() {
  if (fallbackBackend) return fallbackBackend;
  const params = new URLSearchParams(location.search);
  const backend = params.get("backend");
  if (backend) {
    if (backend.startsWith("http://") || backend.startsWith("https://")) {
      return backend.replace(/\/+$/, "");
    }
    return `${location.protocol}//${backend.replace(/\/+$/, "")}`;
  }
  return `${location.protocol}//${location.host}`;
}

async function resolveBackend() {
  const params = new URLSearchParams(location.search);
  if (params.has("backend")) return;

  const devBackend = localDevBackend();
  if (!devBackend) return;

  try {
    const sameOrigin = await fetch(`${backendOrigin()}/api/status`);
    if (sameOrigin.ok) return;
  } catch {
    // Same-origin API is unavailable; try the local backend directly.
  }

  try {
    const direct = await fetch(`${devBackend}/api/status`);
    if (direct.ok) fallbackBackend = devBackend;
  } catch {
    // Keep same-origin routing so reconnects can recover if the backend starts later.
  }
}

function wsUrl() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const origin = backendOrigin().replace(/^https?:/, proto);
  return `${origin}/ws/chat`;
}

function setStatus(online) {
  statusEl.textContent = online ? "online" : "offline";
  statusEl.className = "status " + (online ? "online" : "offline");
}

function addMessage(kind, who, content) {
  const el = document.createElement("div");
  el.className = "msg " + kind;
  if (who) {
    const w = document.createElement("div");
    w.className = "who";
    w.textContent = who;
    el.appendChild(w);
  }
  const body = document.createElement("div");
  body.textContent = content;
  el.appendChild(body);
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
}

function render(data) {
  switch (data.kind) {
    case "system":
      addMessage("system", null, `${data.content}${data.roster ? " · team: " + data.roster.join(", ") : ""}`);
      break;
    case "message": {
      const arrow = data.recipient ? ` → ${data.recipient}` : "";
      addMessage("agent", `${data.sender}${arrow}`, data.content);
      break;
    }
    case "tool_call":
      addMessage("tool", `${data.sender} · ${data.tool}`, data.arguments || "");
      break;
    case "url_imported":
    case "urls_updated":
      void loadUrls();
      break;
    case "error":
      addMessage("error", "error", data.content);
      break;
    default:
      addMessage("system", null, JSON.stringify(data));
  }
}

function connect() {
  const url = wsUrl();
  ws = new WebSocket(url);
  ws.onopen = () => setStatus(true);
  ws.onclose = () => {
    setStatus(false);
    setTimeout(connect, 2000);
  };
  ws.onerror = () => setStatus(false);
  ws.onmessage = (ev) => {
    try {
      render(JSON.parse(ev.data));
    } catch {
      addMessage("system", null, ev.data);
    }
  };
}

function send(text) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    addMessage("error", "error", "Not connected.");
    return;
  }
  ws.send(text);
  addMessage("human", "@Human", text);
}

composer.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = textInput.value.trim();
  if (!text) return;
  send(text);
  textInput.value = "";
});

function handleIngest() {
  const url = urlInput.value.trim();
  if (!url) return;
  send(`@WebIngest Please fetch this page, extract the key knowledge, and store it: ${url}`);
  urlInput.value = "";
  // The backend records the URL as soon as it's routed to @WebIngest; give it a beat.
  setTimeout(loadUrls, 300);
}

ingestBtn.addEventListener("click", handleIngest);
urlInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    handleIngest();
  }
});

function formatTimestamp(iso) {
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

async function loadUrls() {
  const base = backendOrigin();
  try {
    let res = await fetch(`${base}/api/urls`);
    const devBackend = localDevBackend();
    // If running the dev static server on 8080 without a proxy, retry with port 8000.
    if (res.status === 404 && !fallbackBackend && devBackend) {
      try {
        const devRes = await fetch(`${devBackend}/api/urls`);
        if (devRes.ok) {
          fallbackBackend = devBackend;
          res = devRes;
        }
      } catch {
        // ignore dev retry error
      }
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderUrls(data.urls || []);
  } catch (err) {
    urlList.innerHTML = "";
    const li = document.createElement("li");
    li.className = "url-item error";
    li.textContent = `Could not load imported URLs: ${err.message || err}`;
    urlList.appendChild(li);
  }
}

function renderUrls(records) {
  if (urlsTitle) {
    urlsTitle.textContent = records.length > 0 ? `Imported URLs (${records.length})` : "Imported URLs";
  }
  urlList.innerHTML = "";
  if (records.length === 0) {
    const li = document.createElement("li");
    li.className = "url-item empty";
    li.textContent = "No URLs imported yet.";
    urlList.appendChild(li);
    return;
  }
  for (const record of records) {
    const li = document.createElement("li");
    li.className = "url-item";

    const link = document.createElement("a");
    link.href = record.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = record.url;
    li.appendChild(link);

    const meta = document.createElement("div");
    meta.className = "url-meta";
    const times = record.times_submitted > 1 ? ` · submitted ${record.times_submitted}×` : "";
    meta.textContent = `last imported ${formatTimestamp(record.last_seen_at)}${times}`;
    li.appendChild(meta);

    urlList.appendChild(li);
  }
}

urlsRefreshBtn.addEventListener("click", loadUrls);

async function start() {
  await resolveBackend();
  connect();
  await loadUrls();
}

void start();
