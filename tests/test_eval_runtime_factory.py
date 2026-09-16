"""Tests for evaluation task lifecycle isolation."""

from __future__ import annotations

from typing import Any

from akgentic_evals.runtime import run_case_with_factory
from evals.harness import runtime as harness_runtime
from evals.harness.models import KnowledgeCaseInput, KnowledgeEvaluationEnvironment
from evals.harness.runtime import KnowledgeRuntimeFactory


def test_each_task_run_uses_and_shuts_down_a_fresh_team(
    monkeypatch: Any,
) -> None:
    teams: list[FakeTeam] = []
    compositions: list[dict[str, Any]] = []

    class RecordingTeam(FakeTeam):
        def __init__(self, team_card: Any) -> None:
            super().__init__(team_card)
            teams.append(self)

    def record_composition(
        catalog_team: str,
        state_dir: Any,
        *,
        web_tool: Any = None,
        knowledge_tool: Any = None,
    ) -> object:
        compositions.append(
            {
                "catalog_team": catalog_team,
                "state_dir": state_dir,
                "web_tool": web_tool,
                "knowledge_tool": knowledge_tool,
            }
        )
        return object()

    monkeypatch.setattr(harness_runtime, "KnowledgeTeam", RecordingTeam)
    monkeypatch.setattr(harness_runtime, "KnowledgeTeamRuntime", FakeRuntime)
    monkeypatch.setattr(harness_runtime, "load_case_team_card", record_composition)

    factory = KnowledgeRuntimeFactory()
    first = run_case_with_factory(
        KnowledgeCaseInput(message="first", timeout_seconds=1),
        factory,
    )
    second = run_case_with_factory(
        KnowledgeCaseInput(message="second", timeout_seconds=1),
        factory,
    )
    failure = run_case_with_factory(
        KnowledgeCaseInput(
            message="failure",
            timeout_seconds=1,
            environment=KnowledgeEvaluationEnvironment(
                fixture_source_url="https://eval.invalid/unreachable",
                fixture_web_failure="Connection timed out",
            ),
        ),
        factory,
    )

    assert first.final_response == "first"
    assert second.final_response == "second"
    assert failure.final_response == "failure"
    assert len(teams) == 3
    assert teams[0] is not teams[1]
    assert all(team.shutdown_called for team in teams)
    assert all(item["catalog_team"] == "evaluation" for item in compositions)
    assert compositions[2]["web_tool"].delegate.source_url == (
        "https://eval.invalid/unreachable"
    )
    assert compositions[2]["web_tool"].delegate.failure_message == "Connection timed out"


def test_production_task_does_not_construct_fixture_web_tool(monkeypatch: Any) -> None:
    compositions: list[dict[str, Any]] = []

    def record_composition(
        catalog_team: str,
        state_dir: Any,
        *,
        web_tool: Any = None,
        knowledge_tool: Any = None,
    ) -> object:
        compositions.append(
            {
                "catalog_team": catalog_team,
                "web_tool": web_tool,
                "knowledge_tool": knowledge_tool,
            }
        )
        return object()

    monkeypatch.setattr(harness_runtime, "KnowledgeTeam", FakeTeam)
    monkeypatch.setattr(harness_runtime, "KnowledgeTeamRuntime", FakeRuntime)
    monkeypatch.setattr(harness_runtime, "load_case_team_card", record_composition)

    output = run_case_with_factory(
        KnowledgeCaseInput(
            message="Ingest https://coenradie.com/about",
            timeout_seconds=1,
            environment=KnowledgeEvaluationEnvironment(
                fixture_source_url="https://coenradie.com/about",
                fixture_path="not-read-in-production.txt",
            ),
        ),
        KnowledgeRuntimeFactory("production"),
    )

    assert output.final_response == "Ingest https://coenradie.com/about"
    assert compositions == [
        {
            "catalog_team": "production",
            "web_tool": None,
            "knowledge_tool": None,
        }
    ]


class FakeTeam:
    def __init__(self, team_card: Any) -> None:
        self.team_card = team_card
        self.shutdown_called = False

    def shutdown(self) -> None:
        self.shutdown_called = True


class FakeRuntime:
    def __init__(self, team: FakeTeam) -> None:
        self.team = team
        self.event_handler: Any = None

    def start(self, event_handler: Any) -> None:
        self.event_handler = event_handler

    def send(self, turn: Any) -> None:
        from akgentic_evals.events import MessageObserved

        self.event_handler(
            MessageObserved(
                sender="@Manager",
                recipient="@Human",
                message_type="AgentMessage",
                content=turn.message,
            )
        )

    def shutdown(self) -> None:
        self.team.shutdown()
