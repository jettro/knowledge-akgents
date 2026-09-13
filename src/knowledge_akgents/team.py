"""Boot and drive the Akgentic team.

Wiring mirrors the framework's ``agent_team`` example but is driven by a web backend
instead of a CLI loop: the ``HumanProxy`` relays browser input to the team, and a
``WebEventBridge`` streams the resulting traffic back out.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable

from akgentic.agent import AgentMessage
from akgentic.core import ActorSystem, EventSubscriber
from akgentic.team import TeamCard, TeamFactory, TeamRuntime

from knowledge_akgents.events import Publish, WebEventBridge
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
