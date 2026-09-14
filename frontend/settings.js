"use strict";

import { backendFetch, resolveBackend } from "./backend.js?v=2";

const apiStatus = document.getElementById("api-status");
const errorEl = document.getElementById("settings-error");
const refreshButton = document.getElementById("settings-refresh");

function setText(id, value) {
  document.getElementById(id).textContent = value ?? "—";
}

function yesNo(value) {
  if (value === null || value === undefined) return "Not available";
  return value ? "Yes" : "No";
}

function setPill(id, text, tone) {
  const element = document.getElementById(id);
  element.textContent = text.replaceAll("_", " ");
  element.className = `pill ${tone}`;
}

function synchronizationTone(state) {
  if (state === "plausible" || state === "empty") return "good";
  if (state === "out_of_sync") return "bad";
  return "warning";
}

function render(data) {
  const storage = data.storage;
  const qdrant = storage.qdrant;
  const collection = qdrant.collection;
  const urls = storage.imported_urls;
  const synchronization = storage.synchronization;

  apiStatus.textContent = "backend online";
  apiStatus.className = "status online";
  setPill("storage-mode", storage.mode, storage.persistent ? "good" : "warning");
  setText("storage-persistent", yesNo(storage.persistent));
  setText("qdrant-target", qdrant.target || "Not configured");
  setText("qdrant-reachable", yesNo(qdrant.reachable));
  setText(
    "qdrant-collection",
    collection ? `${collection.name} (${collection.exists ? collection.status || "present" : "missing"})` : "—",
  );
  setText("qdrant-points", collection?.points_count);

  const qdrantError = document.getElementById("qdrant-error");
  qdrantError.hidden = !qdrant.error;
  qdrantError.textContent = qdrant.error || "";

  setPill("url-count", `${urls.tracked} tracked`, "neutral");
  setText("urls-tracked", urls.tracked);
  setText("urls-ingested", urls.successfully_ingested);
  setText("urls-failed", urls.failed);

  setPill("sync-state", synchronization.state, synchronizationTone(synchronization.state));
  setText("sync-reason", synchronization.reason);

  setText("model-provider", data.model.provider);
  setText("model-name", data.model.name);
  setText("model-configured", yesNo(data.model.configured));
  setText("web-configured", yesNo(data.web_search.configured));

  setPill("team-status", data.team.status, data.team.status === "running" ? "good" : "warning");
  setText("team-namespace", data.team.catalog_namespace || data.team.name);
  setText("team-id", data.team.team_id);
  setText("team-created", new Date(data.team.created_at).toLocaleString());
}

async function loadSettings() {
  refreshButton.disabled = true;
  errorEl.hidden = true;
  try {
    const response = await backendFetch("/api/system/status");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    render(await response.json());
  } catch (error) {
    apiStatus.textContent = "backend offline";
    apiStatus.className = "status offline";
    errorEl.hidden = false;
    errorEl.textContent = `Could not load system status: ${error.message || error}`;
  } finally {
    refreshButton.disabled = false;
  }
}

refreshButton.addEventListener("click", loadSettings);

async function start() {
  await resolveBackend();
  await loadSettings();
}

void start();
