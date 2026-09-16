"""Knowledge Akgents adapter for the reusable evaluation runtime."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from akgentic_evals.runtime import (
    ConversationTurn,
    EventHandler,
    RuntimeCapabilities,
)
from evals.harness.catalog import TeamCatalog, load_case_team_card
from evals.harness.collector import AkgenticEventAdapter
from evals.harness.fixture_knowledge import FixtureKnowledgeTool, KnowledgeFixture
from evals.harness.fixture_web import FixtureWebTool
from evals.harness.models import KnowledgeCaseInput
from knowledge_akgents.change_aware_web import ChangeAwareWebTool
from knowledge_akgents.team import KnowledgeTeam


class KnowledgeTeamRuntime:
    capabilities = RuntimeCapabilities(
        request_correlation=True,
        isolated_execution=True,
        quiescence_detection=False,
        trace_context=True,
    )

    def __init__(self, team: KnowledgeTeam) -> None:
        self._team = team
        self._event_adapter: AkgenticEventAdapter | None = None

    def start(self, event_handler: EventHandler) -> None:
        self._event_adapter = AkgenticEventAdapter(event_handler)
        self._team.start(publish=lambda _: None, subscribers=(self._event_adapter,))

    def send(self, turn: ConversationTurn) -> None:
        self._team.send(turn.message, turn.target)

    def shutdown(self) -> None:
        self._team.shutdown()


class KnowledgeRuntimeFactory:
    """Build an isolated Knowledge Akgents runtime from application configuration."""

    def __init__(self, catalog_team: TeamCatalog = "evaluation") -> None:
        self._catalog_team = catalog_team

    @contextmanager
    def runtime(
        self,
        inputs: KnowledgeCaseInput,
    ) -> Iterator[KnowledgeTeamRuntime]:
        with TemporaryDirectory(prefix="knowledge-akgents-eval-") as state_dir:
            yield KnowledgeTeamRuntime(
                _build_team(inputs, Path(state_dir), self._catalog_team)
            )


def _build_team(
    inputs: KnowledgeCaseInput,
    state_dir: Path,
    catalog_team: TeamCatalog,
) -> KnowledgeTeam:
    environment = inputs.environment
    web_tool = None
    if catalog_team == "evaluation" and environment.fixture_source_url:
        content = (
            Path(environment.fixture_path).read_text(encoding="utf-8")
            if environment.fixture_path
            else ""
        )
        content_sequence = [
            Path(fixture_path).read_text(encoding="utf-8")
            for fixture_path in environment.fixture_paths
        ]
        web_tool = ChangeAwareWebTool(
            repository_path=state_dir / "urls.json",
            delegate=FixtureWebTool(
                source_url=environment.fixture_source_url,
                content=content,
                content_sequence=content_sequence,
                failure_message=environment.fixture_web_failure,
            ),
        )

    knowledge_tool = None
    if environment.knowledge_fixture is not None:
        knowledge_tool = FixtureKnowledgeTool(
            records=environment.knowledge_fixture.records
        )
    elif environment.knowledge_fixture_path:
        fixture = KnowledgeFixture.model_validate_json(
            Path(environment.knowledge_fixture_path).read_text(encoding="utf-8")
        )
        knowledge_tool = FixtureKnowledgeTool(records=fixture.records)

    team_card = load_case_team_card(
        catalog_team,
        state_dir,
        web_tool=web_tool,
        knowledge_tool=knowledge_tool,
    )
    return KnowledgeTeam(team_card)
