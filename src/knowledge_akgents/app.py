"""FastAPI backend hosting the Akgentic team and bridging it to the browser."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from knowledge_akgents.settings import settings
from knowledge_akgents.team import KnowledgeTeam

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
team = KnowledgeTeam()


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


@app.get("/")
async def root() -> JSONResponse:
    return JSONResponse(
        {
            "service": "knowledge-akgents",
            "model": settings.llm_model,
            "qdrant": settings.qdrant_enabled,
            "roster": team.roster(),
        }
    )


@app.get("/api/team")
async def get_team() -> JSONResponse:
    return JSONResponse({"members": team.roster()})


@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket) -> None:
    await ws.accept()
    q = manager.register()
    await ws.send_json({"kind": "system", "content": "connected", "roster": team.roster()})

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
