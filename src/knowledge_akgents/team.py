"""Boot and drive the Akgentic team.

Wiring mirrors the framework's ``agent_team`` example but is driven by a web backend
instead of a CLI loop: the ``HumanProxy`` relays browser input to the team, and a
``WebEventBridge`` streams the resulting traffic back out.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from akgentic.agent import AgentMessage
from akgentic.core import ActorSystem, EventSubscriber
from akgentic.team import (
    Process,
    TeamCard,
    TeamFactory,
    TeamManager,
    TeamRuntime,
    TeamStatus,
    YamlEventStore,
)

from knowledge_akgents.catalog import PRODUCTION_CATALOG_NAMESPACE, load_team_card
from knowledge_akgents.events import Publish, WebEventBridge
from knowledge_akgents.repository import UrlRepository
from knowledge_akgents.settings import Settings
from knowledge_akgents.trace_context import attach_message_context

logger = logging.getLogger(__name__)


class KnowledgeTeam:
    """Owns the actor system and exposes a small send/roster/shutdown surface."""

    def __init__(self, team_card: TeamCard) -> None:
        self._system: ActorSystem | None = None
        self._runtime: TeamRuntime | None = None
        self._started = False
        self._team_card = team_card

    def start(
        self,
        publish: Publish,
        subscribers: Iterable[EventSubscriber] = (),
    ) -> None:
        if self._started:
            return

        self._system = ActorSystem()
        self._team_card.message_types = [AgentMessage]
        self._runtime = TeamFactory.build(
            self._team_card,
            self._system,
            subscribers=[WebEventBridge(publish), *subscribers],
        )

        time.sleep(0.3)  # let actors initialise
        self._started = True
        logger.info("Knowledge team started: %s", self.roster())

    def send(self, text: str, target: str | None = None) -> None:
        """Deliver a human message, optionally routed to a specific @agent."""
        if not self._started or self._runtime is None:
            raise RuntimeError("Team is not started")

        if target:
            name = target if target.startswith("@") else f"@{target}"
        else:
            name = "@Manager"
        message = AgentMessage(content=text)
        attach_message_context(message)
        self._runtime.send_to(name, message)

    def roster(self) -> list[str]:
        if not self._started or self._runtime is None:
            return []
        try:
            team = self._runtime.orchestrator_proxy.get_team()
            names = {getattr(a, "name", str(a)) for a in team}
            # Show agents (@-prefixed), not the internal tool actors (#-prefixed).
            return sorted(n for n in names if n.startswith("@") and n != "@Human")
        except Exception:  # pragma: no cover - defensive
            return ["@Knowledge", "@Manager", "@WebIngest"]

    def shutdown(self) -> None:
        if self._system is not None:
            self._system.shutdown()
            self._system = None
            self._runtime = None
            self._started = False


class ActiveTeamStore:
    """Atomically persist the runtime UUID selected by the application."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> UUID | None:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return UUID(str(data["team_id"]))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            logger.warning("Could not read active team selection from %s", self._path)
            return None

    def save(self, team_id: UUID) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"team_id": str(team_id)}, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self._path)


class ManagedKnowledgeTeams:
    """Own persistent team instances and expose exactly one active runtime."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._system: ActorSystem | None = None
        self._manager: TeamManager | None = None
        self._event_store = YamlEventStore(settings.team_data_dir)
        self._active_store = ActiveTeamStore(settings.active_team_file)
        self._runtime: TeamRuntime | None = None
        self._process: Process | None = None
        self._url_repository: UrlRepository | None = None
        self._lock = threading.RLock()
        self._started = False

    def start(self, publish: Publish) -> None:
        with self._lock:
            if self._started:
                return
            self._system = ActorSystem()
            self._manager = TeamManager(
                actor_system=self._system,
                event_store=self._event_store,
                subscribers=[WebEventBridge(publish)],
            )
            selected = self._select_startup_process()
            if selected is None:
                self._create_runtime(PRODUCTION_CATALOG_NAMESPACE)
            else:
                self._resume_process(selected)
            self._started = True
            time.sleep(0.3)
            logger.info(
                "Managed knowledge team started: %s (%s)",
                self.catalog_namespace,
                self.id,
            )

    def _select_startup_process(self) -> Process | None:
        selected_id = self._active_store.load()
        if selected_id is not None:
            selected = self._event_store.load_team(selected_id)
            if selected is not None:
                return selected
            logger.warning("Previously active team %s no longer exists", selected_id)

        candidates = [
            process
            for process in self._event_store.list_teams()
            if process.catalog_namespace == PRODUCTION_CATALOG_NAMESPACE
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda process: process.updated_at)

    def _resume_process(self, process: Process) -> None:
        manager = self._require_manager()
        if process.status == TeamStatus.RUNNING:
            # The sample owns one backend process. A persisted RUNNING process at
            # startup is therefore stale state left by an ungraceful shutdown.
            manager.stop_team(process.team_id)
        runtime = manager.resume_team(process.team_id)
        restored = manager.get_team(process.team_id)
        if restored is None:
            raise RuntimeError(f"Resumed team {process.team_id} was not persisted")
        self._set_active(runtime, restored)

    def _create_runtime(self, namespace: str) -> None:
        manager = self._require_manager()
        team_id = uuid4()
        team_card = load_team_card(
            namespace,
            web_repository_path=self._settings.urls_file_for(team_id),
        )
        team_card.message_types = [AgentMessage]
        runtime = manager.create_team(
            team_card,
            team_id=team_id,
            catalog_namespace=namespace,
        )
        process = manager.get_team(team_id)
        if process is None:
            raise RuntimeError(f"Created team {team_id} was not persisted")
        self._set_active(runtime, process)

    def _set_active(self, runtime: TeamRuntime, process: Process) -> None:
        self._runtime = runtime
        self._process = process
        self._url_repository = UrlRepository(self._settings.urls_file_for(process.team_id))
        self._active_store.save(process.team_id)

    def create_and_activate(self, namespace: str) -> Process:
        with self._lock:
            previous = self._process
            self._stop_active()
            try:
                self._create_runtime(namespace)
            except Exception:
                if previous is not None:
                    self._resume_process(previous)
                raise
            return self.active_process

    def activate(self, team_id: UUID) -> Process:
        with self._lock:
            if self._process is not None and self._process.team_id == team_id:
                return self._process
            target = self._event_store.load_team(team_id)
            if target is None:
                raise ValueError(f"Team {team_id} not found")
            previous = self._process
            self._stop_active()
            try:
                self._resume_process(target)
            except Exception:
                if previous is not None:
                    self._resume_process(previous)
                raise
            return self.active_process

    def _stop_active(self) -> None:
        if self._process is None:
            return
        self._require_manager().stop_team(self._process.team_id)
        stopped = self._event_store.load_team(self._process.team_id)
        if stopped is not None:
            self._process = stopped
        self._runtime = None

    def send(self, text: str, target: str | None = None) -> None:
        with self._lock:
            runtime = self._runtime
            if not self._started or runtime is None:
                raise RuntimeError("Team is not started")
            if target:
                name = target if target.startswith("@") else f"@{target}"
            else:
                name = "@Manager"
            message = AgentMessage(content=text)
            attach_message_context(message)
            runtime.send_to(name, message)

    def roster(self) -> list[str]:
        with self._lock:
            runtime = self._runtime
            if runtime is None:
                return []
            try:
                members = runtime.orchestrator_proxy.get_team()
                names = {getattr(member, "name", str(member)) for member in members}
                return sorted(
                    name
                    for name in names
                    if name.startswith("@") and name != "@Human"
                )
            except Exception:  # pragma: no cover - defensive
                return ["@Knowledge", "@Manager", "@WebIngest"]

    def list_instances(self) -> list[Process]:
        return sorted(
            self._event_store.list_teams(),
            key=lambda process: process.created_at,
            reverse=True,
        )

    @property
    def active_process(self) -> Process:
        if self._process is None:
            raise RuntimeError("No active team")
        return self._process

    @property
    def id(self) -> UUID:
        return self.active_process.team_id

    @property
    def catalog_namespace(self) -> str | None:
        return self.active_process.catalog_namespace

    @property
    def url_repository(self) -> UrlRepository:
        if self._url_repository is None:
            raise RuntimeError("No active URL repository")
        return self._url_repository

    def shutdown(self) -> None:
        with self._lock:
            if self._manager is not None and self._process is not None:
                self._manager.stop_team(self._process.team_id)
            if self._system is not None:
                self._system.shutdown()
            self._system = None
            self._manager = None
            self._runtime = None
            self._started = False

    def _require_manager(self) -> TeamManager:
        if self._manager is None:
            raise RuntimeError("Team manager is not started")
        return self._manager


def process_dict(process: Process, *, active: bool) -> dict[str, object]:
    """Project persisted framework state to the application's API shape."""
    return {
        "team_id": str(process.team_id),
        "catalog_namespace": process.catalog_namespace,
        "name": process.team_name,
        "description": process.team_description,
        "status": process.status.value,
        "active": active,
        "created_at": _isoformat(process.created_at),
        "updated_at": _isoformat(process.updated_at),
    }


def _isoformat(value: datetime) -> str:
    return value.isoformat()
