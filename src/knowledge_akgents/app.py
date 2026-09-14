"""FastAPI backend hosting the Akgentic team and bridging it to the browser."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from knowledge_akgents.catalog import list_team_definitions
from knowledge_akgents.repository import UrlRecord
from knowledge_akgents.settings import settings
from knowledge_akgents.storage_status import storage_status
from knowledge_akgents.team import ManagedKnowledgeTeams, process_dict

logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("knowledge_akgents")


class ConnectionManager:
    """Fan-out of team events to every connected websocket."""

    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[dict[str, Any]]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def register(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._queues.add(q)
        return q

    def unregister(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._queues.discard(q)

    def _broadcast(self, data: dict[str, Any]) -> None:
        for q in list(self._queues):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(data)

    def publish_threadsafe(self, data: dict[str, Any]) -> None:
        """Called from actor threads; hops onto the asyncio loop."""
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._broadcast, data)


manager = ConnectionManager()
team = ManagedKnowledgeTeams(settings)

_URL_RE = re.compile(r"https?://[^\s<>\"'\[\]{}]+")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    manager.bind_loop(asyncio.get_running_loop())
    _warn_missing_config()
    team.start(publish=manager.publish_threadsafe)
    logger.info("Team roster: %s", team.roster())
    try:
        yield
    finally:
        team.shutdown()


app = FastAPI(title="Knowledge Akgents", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/info")
@app.get("/api/status")
async def api_info() -> JSONResponse:
    return JSONResponse(
        {
            "service": "knowledge-akgents",
            "model": settings.llm_model,
            "qdrant": settings.qdrant_enabled,
            "roster": team.roster(),
            "team": process_dict(team.active_process, active=True),
        }
    )


@app.get("/api/team")
async def get_team() -> JSONResponse:
    return JSONResponse(
        {
            "members": team.roster(),
            "team": process_dict(team.active_process, active=True),
        }
    )


class CreateTeamRequest(BaseModel):
    catalog_namespace: str


@app.get("/api/team-definitions")
async def get_team_definitions() -> JSONResponse:
    return JSONResponse({"definitions": list_team_definitions()})


@app.get("/api/team-instances")
async def get_team_instances() -> JSONResponse:
    active_id = team.id
    return JSONResponse(
        {
            "active_team_id": str(active_id),
            "instances": [
                process_dict(process, active=process.team_id == active_id)
                for process in team.list_instances()
            ],
        }
    )


@app.post("/api/team-instances")
async def create_team_instance(request: CreateTeamRequest) -> JSONResponse:
    definitions = {
        definition["namespace"] for definition in list_team_definitions()
    }
    if request.catalog_namespace not in definitions:
        raise HTTPException(status_code=404, detail="Catalog team definition not found")
    try:
        process = await asyncio.to_thread(
            team.create_and_activate,
            request.catalog_namespace,
        )
    except Exception as exc:
        logger.exception("Could not create team from %s", request.catalog_namespace)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    manager.publish_threadsafe(
        {
            "kind": "team_changed",
            "team": process_dict(process, active=True),
            "roster": team.roster(),
        }
    )
    return JSONResponse(process_dict(process, active=True), status_code=201)


@app.post("/api/team-instances/{team_id}/activate")
async def activate_team_instance(team_id: UUID) -> JSONResponse:
    try:
        process = await asyncio.to_thread(team.activate, team_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Could not activate team %s", team_id)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    manager.publish_threadsafe(
        {
            "kind": "team_changed",
            "team": process_dict(process, active=True),
            "roster": team.roster(),
        }
    )
    return JSONResponse(process_dict(process, active=True))


@app.get("/api/system/status")
async def get_system_status() -> JSONResponse:
    storage = await asyncio.to_thread(
        storage_status,
        settings,
        team.url_repository,
        team.id,
    )
    return JSONResponse(
        {
            "service": "knowledge-akgents",
            "model": {
                "provider": settings.llm_provider,
                "name": settings.llm_model,
                "configured": bool(settings.openai_api_key),
            },
            "web_search": {
                "provider": "tavily",
                "configured": bool(settings.tavily_api_key),
            },
            "storage": storage,
            "roster": team.roster(),
            "team": process_dict(team.active_process, active=True),
        }
    )


@app.get("/api/urls")
async def get_urls() -> JSONResponse:
    """URLs previously submitted for ingestion, most recent first."""
    return JSONResponse(
        {"urls": [asdict(record) for record in team.url_repository.list()]}
    )


@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket) -> None:
    await ws.accept()
    q = manager.register()
    await ws.send_json(
        {
            "kind": "system",
            "content": "connected",
            "roster": team.roster(),
            "team": process_dict(team.active_process, active=True),
        }
    )

    async def pump_out() -> None:
        while True:
            data = await q.get()
            await ws.send_json(data)

    out_task = asyncio.create_task(pump_out())
    try:
        while True:
            raw = await ws.receive_text()
            text, target = _parse_input(raw)
            if not text:
                continue
            if (target and target.lstrip("@").lower() == "webingest") or _extract_urls(text):
                _track_urls(text)
            try:
                team.send(text, target)
            except Exception as exc:  # surface routing/user errors to the client
                await ws.send_json({"kind": "error", "content": str(exc)})
    except WebSocketDisconnect:
        pass
    finally:
        out_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await out_task
        manager.unregister(q)


def _parse_input(raw: str) -> tuple[str, str | None]:
    """Accept either plain text or JSON ``{"text": ..., "target": ...}``.

    A leading ``@Agent`` token in plain text routes to that agent.
    """
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            obj = json.loads(raw)
            return str(obj.get("text", "")).strip(), (obj.get("target") or None)
        except json.JSONDecodeError:
            pass
    if raw.startswith("@"):
        parts = raw.split(" ", 1)
        target = parts[0][1:]
        text = parts[1].strip() if len(parts) > 1 else ""
        return text, target or None
    return raw, None


def _extract_urls(text: str) -> list[str]:
    """Pull out unique http(s) URLs from a chat message, in order of appearance."""
    seen: dict[str, None] = {}
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(").,;!?\"'")
        seen.setdefault(url, None)
    return list(seen.keys())


def _track_url_single(url: str) -> UrlRecord | None:
    """Record a single URL and broadcast its import to connected web clients."""
    try:
        record = team.url_repository.add(url)
        manager.publish_threadsafe({"kind": "url_imported", "record": asdict(record)})
        return record
    except Exception:  # pragma: no cover - defensive, must never break ingestion
        logger.exception("Failed to record ingested URL: %s", url)
        return None


def _track_urls(text: str) -> list[UrlRecord]:
    """Record any URL(s) so they show up in the imported-URLs list."""
    records: list[UrlRecord] = []
    for url in _extract_urls(text):
        rec = _track_url_single(url)
        if rec is not None:
            records.append(rec)
    return records


def _warn_missing_config() -> None:
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY is not set — agents cannot call the LLM.")
    if not settings.tavily_api_key:
        logger.warning("TAVILY_API_KEY is not set — web fetch/crawl will be non-functional.")
    if not settings.qdrant_enabled:
        logger.warning(
            "AKGENTIC_QDRANT_URL is not set — knowledge base uses the in-memory backend "
            "(non-persistent)."
        )


# Mount static files for the frontend if the directory exists
frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if frontend_dir.exists() and (frontend_dir / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
else:
    @app.get("/")
    async def root() -> JSONResponse:
        return JSONResponse(
            {
                "service": "knowledge-akgents",
                "model": settings.llm_model,
                "qdrant": settings.qdrant_enabled,
                "roster": team.roster(),
                "team": process_dict(team.active_process, active=True),
            }
        )
