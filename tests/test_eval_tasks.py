"""Tests for evaluation task lifecycle isolation."""

from __future__ import annotations

from typing import Any

from evals import tasks
from evals.models import TeamCaseInput, TeamCaseOutput


def test_each_task_run_uses_and_shuts_down_a_fresh_team(
    monkeypatch: Any,
) -> None:
    teams: list[FakeTeam] = []

    class RecordingTeam(FakeTeam):
        def __init__(self, web_tool: Any = None, knowledge_tool: Any = None) -> None:
            super().__init__(web_tool, knowledge_tool)
            teams.append(self)

    monkeypatch.setattr(tasks, "KnowledgeTeam", RecordingTeam)
    monkeypatch.setattr(tasks, "EvaluationEventCollector", FakeCollector)

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
    assert teams[2].web_tool.delegate.source_url == "https://eval.invalid/unreachable"
    assert teams[2].web_tool.delegate.failure_message == "Connection timed out"


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
    def __init__(self, web_tool: Any = None, knowledge_tool: Any = None) -> None:
        self.web_tool = web_tool
        self.knowledge_tool = knowledge_tool
        self.collector: FakeCollector | None = None
        self.shutdown_called = False

    def start(self, publish: Any, subscribers: tuple[FakeCollector, ...]) -> None:
        self.collector = subscribers[0]

    def send(self, text: str, target: str | None = None) -> None:
        assert self.collector is not None
        self.collector.response = text

    def shutdown(self) -> None:
        self.shutdown_called = True
