"""Tests for evaluation task lifecycle isolation."""

from __future__ import annotations

from typing import Any

from evals.harness import tasks
from evals.harness.models import TeamCaseInput, TeamCaseOutput


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

    monkeypatch.setattr(tasks, "KnowledgeTeam", RecordingTeam)
    monkeypatch.setattr(tasks, "EvaluationEventCollector", FakeCollector)
    monkeypatch.setattr(tasks, "load_case_team_card", record_composition)

    first = tasks.run_team_case(TeamCaseInput(message="first", timeout_seconds=1))
    second = tasks.run_team_case(TeamCaseInput(message="second", timeout_seconds=1))
    failure = tasks.run_team_case(
        TeamCaseInput(
            message="failure",
            timeout_seconds=1,
            fixture_source_url="https://eval.invalid/unreachable",
            fixture_web_failure="Connection timed out",
        )
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

    monkeypatch.setattr(tasks, "KnowledgeTeam", FakeTeam)
    monkeypatch.setattr(tasks, "EvaluationEventCollector", FakeCollector)
    monkeypatch.setattr(tasks, "load_case_team_card", record_composition)

    output = tasks.run_team_case(
        TeamCaseInput(
            message="Ingest https://coenradie.com/about",
            timeout_seconds=1,
            fixture_source_url="https://coenradie.com/about",
            fixture_path="not-read-in-production.txt",
        ),
        catalog_team="production",
    )

    assert output.final_response == "Ingest https://coenradie.com/about"
    assert compositions == [
        {
            "catalog_team": "production",
            "web_tool": None,
            "knowledge_tool": None,
        }
    ]


class FakeCollector:
    def __init__(self) -> None:
        self.response = ""

    def wait_for_human_responses(
        self,
        expected_count: int,
        timeout_seconds: float,
    ) -> TeamCaseOutput:
        responses = [self.response] if expected_count else []
        return TeamCaseOutput(
            final_response=responses[-1] if responses else None,
            human_responses=responses,
            completion_reason="human_response",
            messages=[],
            tool_calls=[],
            tool_returns=[],
            errors=[],
        )


class FakeTeam:
    def __init__(self, team_card: Any) -> None:
        self.team_card = team_card
        self.collector: FakeCollector | None = None
        self.shutdown_called = False

    def start(self, publish: Any, subscribers: tuple[FakeCollector, ...]) -> None:
        self.collector = subscribers[0]

    def send(self, text: str, target: str | None = None) -> None:
        assert self.collector is not None
        self.collector.response = text

    def shutdown(self) -> None:
        self.shutdown_called = True
