"""Task adapters that drive Knowledge Akgents for one evaluation case."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from evals.collector import EvaluationEventCollector
from evals.fixture_knowledge import FixtureKnowledgeTool, KnowledgeFixture
from evals.fixture_web import FixtureWebTool
from evals.models import TeamCaseInput, TeamCaseOutput
from knowledge_akgents.change_aware_web import ChangeAwareWebTool
from knowledge_akgents.team import KnowledgeTeam


def run_team_case(inputs: TeamCaseInput) -> TeamCaseOutput:
    with TemporaryDirectory(prefix="knowledge-akgents-eval-") as state_dir:
        return _run_team_case(inputs, Path(state_dir))


def _run_team_case(inputs: TeamCaseInput, state_dir: Path) -> TeamCaseOutput:
    web_tool = None
    if inputs.fixture_source_url:
        content = (
            Path(inputs.fixture_path).read_text(encoding="utf-8")
            if inputs.fixture_path
            else ""
        )
        content_sequence = [
            Path(fixture_path).read_text(encoding="utf-8")
            for fixture_path in inputs.fixture_paths
        ]
        web_tool = ChangeAwareWebTool(
            repository_path=state_dir / "urls.json",
            delegate=FixtureWebTool(
                source_url=inputs.fixture_source_url,
                content=content,
                content_sequence=content_sequence,
                failure_message=inputs.fixture_web_failure,
            ),
        )

    knowledge_tool = None
    if inputs.knowledge_fixture_path:
        fixture = KnowledgeFixture.model_validate_json(
            Path(inputs.knowledge_fixture_path).read_text(encoding="utf-8")
        )
        knowledge_tool = FixtureKnowledgeTool(records=fixture.records)

    collector = EvaluationEventCollector()
    team = KnowledgeTeam(web_tool=web_tool, knowledge_tool=knowledge_tool)
    try:
        team.start(publish=lambda _: None, subscribers=(collector,))
        output = collector.wait_for_human_responses(0, 0)
        for response_count, turn in enumerate(inputs.ordered_turns(), start=1):
            team.send(turn.message, turn.target)
            output = collector.wait_for_human_responses(
                response_count,
                inputs.timeout_seconds,
            )
            if output.completion_reason != "human_response":
                break
        return output
    finally:
        team.shutdown()
