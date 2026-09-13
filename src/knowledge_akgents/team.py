"""Boot and drive the Akgentic team.

Wiring mirrors the framework's ``agent_team`` example but is driven by a web backend
instead of a CLI loop: the ``HumanProxy`` relays browser input to the team, and a
``WebEventBridge`` streams the resulting traffic back out.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from typing import Any

from akgentic.agent import AgentMessage, BaseAgent, HumanProxy
from akgentic.core import ActorSystem, BaseConfig, EventSubscriber, Orchestrator
from akgentic.tool.core import ToolCard

from knowledge_akgents.agents import all_cards, knowledge_card, manager_card, webingest_card
from knowledge_akgents.events import Publish, WebEventBridge

logger = logging.getLogger(__name__)


class KnowledgeTeam:
    """Owns the actor system and exposes a small send/roster/shutdown surface."""

    def __init__(
        self,
        web_tool: ToolCard | None = None,
        knowledge_tool: ToolCard | None = None,
    ) -> None:
        self._system: ActorSystem | None = None
        self._orchestrator: Any = None
        self._human: Any = None
        self._manager_addr: Any = None
        self._started = False
        self._web_tool = web_tool
        self._knowledge_tool = knowledge_tool

    def start(
        self,
        publish: Publish,
        subscribers: Iterable[EventSubscriber] = (),
    ) -> None:
        if self._started:
            return

        self._system = ActorSystem()

        orchestrator_addr = self._system.createActor(
            Orchestrator, config=BaseConfig(name="@Orchestrator", role="Orchestrator")
        )
        self._orchestrator = self._system.proxy_ask(orchestrator_addr, Orchestrator)

        # Stream team traffic to the web layer.
        self._orchestrator.subscribe(WebEventBridge(publish))
        for subscriber in subscribers:
            self._orchestrator.subscribe(subscriber)

        # Register the role catalog.
        self._orchestrator.register_agent_profiles(all_cards(self._web_tool, self._knowledge_tool))

        # Human proxy: the browser's seat at the table.
        human_addr = self._orchestrator.createActor(
            HumanProxy, config=BaseConfig(name="@Human", role="Human")
        )
        self._human = self._system.proxy_tell(human_addr, HumanProxy)

        # Manager and the two specialists, created as peers under the orchestrator so
        # team assembly never blocks on one agent's health. Routing between them is by
        # @name via the orchestrator, not by parent/child hierarchy.
        self._manager_addr = self._orchestrator.createActor(
            BaseAgent, config=manager_card().get_config_copy()
        )
        self._orchestrator.createActor(
            BaseAgent,
            config=knowledge_card(self._knowledge_tool).get_config_copy(),
        )
        self._orchestrator.createActor(
            BaseAgent,
            config=webingest_card(self._web_tool).get_config_copy(),
        )

        time.sleep(0.3)  # let actors initialise
        self._started = True
        logger.info("Knowledge team started: %s", self.roster())

    def send(self, text: str, target: str | None = None) -> None:
        """Deliver a human message, optionally routed to a specific @agent."""
        if not self._started or self._human is None:
            raise RuntimeError("Team is not started")

        recipient_addr = self._manager_addr
        if target:
            name = target if target.startswith("@") else f"@{target}"
            found = self._orchestrator.get_team_member(name)
            if found is None:
                raise ValueError(f"Unknown agent: {name}")
            recipient_addr = found

        self._human.send(recipient_addr, AgentMessage(content=text))

    def roster(self) -> list[str]:
        if not self._started or self._orchestrator is None:
            return []
        try:
            team = self._orchestrator.get_team()
            names = {getattr(a, "name", str(a)) for a in team}
            # Show agents (@-prefixed), not the internal tool actors (#-prefixed).
            return sorted(n for n in names if n.startswith("@") and n != "@Human")
        except Exception:  # pragma: no cover - defensive
            return ["@Knowledge", "@Manager", "@WebIngest"]

    def shutdown(self) -> None:
        if self._system is not None:
            self._system.shutdown()
            self._system = None
            self._started = False
