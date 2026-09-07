"use strict";

const log = document.getElementById("log");
const statusEl = document.getElementById("status");
const composer = document.getElementById("composer");
const textInput = document.getElementById("text");
const urlInput = document.getElementById("url");
const ingestBtn = document.getElementById("ingest");

let ws = null;

function wsUrl() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  // Same origin; nginx proxies /ws/chat to the backend. Override with ?backend=host:port.
  const params = new URLSearchParams(location.search);
  const backend = params.get("backend");
  const host = backend || location.host;
  return `${proto}//${host}/ws/chat`;
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
    case "error":
      addMessage("error", "error", data.content);
      break;
    default:
      addMessage("system", null, JSON.stringify(data));
  }
}

function connect() {
  ws = new WebSocket(wsUrl());
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

ingestBtn.addEventListener("click", () => {
  const url = urlInput.value.trim();
  if (!url) return;
  send(`@WebIngest Please fetch this page, extract the key knowledge, and store it: ${url}`);
  urlInput.value = "";
});

connect();
