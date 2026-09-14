"use strict";

import { backendFetch, resolveBackend } from "./backend.js?v=2";

const apiStatus = document.getElementById("api-status");
const errorEl = document.getElementById("teams-error");
const refreshButton = document.getElementById("teams-refresh");
const activeTeamEl = document.getElementById("active-team");
const activeStatusEl = document.getElementById("active-team-status");
const instancesEl = document.getElementById("team-instances");
const definitionsEl = document.getElementById("team-definitions");

function formatTimestamp(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function shortId(value) {
  return value ? `${value.slice(0, 8)}…${value.slice(-4)}` : "—";
}

function details(instance) {
  const wrapper = document.createElement("div");
  wrapper.className = "team-card-details";

  const title = document.createElement("h4");
  title.textContent = instance.catalog_namespace || instance.name || "Unnamed team";
  wrapper.appendChild(title);

  const metadata = document.createElement("p");
  metadata.className = "muted";
  metadata.textContent = `${shortId(instance.team_id)} · created ${formatTimestamp(instance.created_at)}`;
  wrapper.appendChild(metadata);
  return wrapper;
}

function renderActive(instance) {
  activeTeamEl.innerHTML = "";
  activeTeamEl.appendChild(details(instance));

  const badge = document.createElement("span");
  badge.className = "team-active-badge";
  badge.textContent = "Loaded automatically on restart";
  activeTeamEl.appendChild(badge);

  activeStatusEl.textContent = instance.status;
  activeStatusEl.className = `pill ${instance.status === "running" ? "good" : "warning"}`;
}

function actionButton(label, handler, className = "secondary-button") {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = label;
  button.addEventListener("click", handler);
  return button;
}

function renderInstances(instances) {
  instancesEl.innerHTML = "";
  for (const instance of instances) {
    const card = document.createElement("article");
    card.className = `team-list-card${instance.active ? " active" : ""}`;
    card.appendChild(details(instance));

    const actions = document.createElement("div");
    actions.className = "team-card-actions";
    if (instance.active) {
      const badge = document.createElement("span");
      badge.className = "pill good";
      badge.textContent = "active";
      actions.appendChild(badge);
    } else {
      actions.appendChild(
        actionButton("Activate", () => activateTeam(instance.team_id)),
      );
    }
    card.appendChild(actions);
    instancesEl.appendChild(card);
  }
}

function renderDefinitions(definitions) {
  definitionsEl.innerHTML = "";
  for (const definition of definitions) {
    const card = document.createElement("article");
    card.className = "team-list-card";

    const content = document.createElement("div");
    content.className = "team-card-details";
    const title = document.createElement("h4");
    title.textContent = definition.name || definition.namespace;
    content.appendChild(title);
    const description = document.createElement("p");
    description.className = "muted";
    description.textContent = definition.description || definition.namespace;
    content.appendChild(description);
    card.appendChild(content);

    const actions = document.createElement("div");
    actions.className = "team-card-actions";
    actions.appendChild(
      actionButton("Create instance", () => createTeam(definition.namespace)),
    );
    card.appendChild(actions);
    definitionsEl.appendChild(card);
  }
}

async function apiRequest(path, options = undefined) {
  const response = await backendFetch(path, options);
  if (response.ok) return response.json();
  let detail = `HTTP ${response.status}`;
  try {
    const body = await response.json();
    detail = body.detail || detail;
  } catch {
    // Keep the status-based message when the response has no JSON body.
  }
  throw new Error(detail);
}

async function activateTeam(teamId) {
  await performChange(() =>
    apiRequest(`/api/team-instances/${teamId}/activate`, { method: "POST" }),
  );
}

async function createTeam(namespace) {
  await performChange(() =>
    apiRequest("/api/team-instances", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ catalog_namespace: namespace }),
    }),
  );
}

async function performChange(operation) {
  errorEl.hidden = true;
  refreshButton.disabled = true;
  try {
    await operation();
    await loadTeams();
  } catch (error) {
    errorEl.hidden = false;
    errorEl.textContent = `Could not change active team: ${error.message || error}`;
  } finally {
    refreshButton.disabled = false;
  }
}

async function loadTeams() {
  refreshButton.disabled = true;
  errorEl.hidden = true;
  try {
    const [instanceData, definitionData] = await Promise.all([
      apiRequest("/api/team-instances"),
      apiRequest("/api/team-definitions"),
    ]);
    const active = instanceData.instances.find((instance) => instance.active);
    if (!active) throw new Error("The backend did not report an active team");
    renderActive(active);
    renderInstances(instanceData.instances);
    renderDefinitions(definitionData.definitions);
    apiStatus.textContent = "backend online";
    apiStatus.className = "status online";
  } catch (error) {
    apiStatus.textContent = "backend offline";
    apiStatus.className = "status offline";
    errorEl.hidden = false;
    errorEl.textContent = `Could not load teams: ${error.message || error}`;
  } finally {
    refreshButton.disabled = false;
  }
}

refreshButton.addEventListener("click", loadTeams);

async function start() {
  await resolveBackend();
  await loadTeams();
}

void start();
