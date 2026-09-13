"use strict";

let fallbackBackend = null;

function localDevBackend() {
  if (location.port !== "8080") return null;
  return `${location.protocol}//${location.hostname}:8000`;
}

export function backendOrigin() {
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

export async function resolveBackend() {
  const params = new URLSearchParams(location.search);
  if (params.has("backend")) {
    preserveBackendParameter(params.get("backend"));
    return;
  }

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
    // Keep same-origin routing so later refreshes can recover.
  }
}

function preserveBackendParameter(backend) {
  for (const link of document.querySelectorAll("a[data-backend-link]")) {
    const target = new URL(link.href, location.href);
    target.searchParams.set("backend", backend);
    link.href = target.toString();
  }
}

export async function backendFetch(path) {
  let response = await fetch(`${backendOrigin()}${path}`);
  const devBackend = localDevBackend();
  if (response.status === 404 && !fallbackBackend && devBackend) {
    try {
      const direct = await fetch(`${devBackend}${path}`);
      if (direct.ok) {
        fallbackBackend = devBackend;
        response = direct;
      }
    } catch {
      // Return the original response so the caller can report its status.
    }
  }
  return response;
}
