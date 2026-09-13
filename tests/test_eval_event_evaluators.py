"""Tests for deterministic event-based evaluators."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from evals.event_evaluators import (
    DidNotCallTools,
    FollowedMessageRoute,
    HumanResponseContainsAnyTerm,
    HumanResponseContainsTerms,
    ToolCallsSucceeded,
    _contains_expected,
    _is_ordered_subsequence,
)
from evals.models import MessageRecord, TeamCaseOutput, ToolCallRecord, ToolReturnRecord


def test_route_matches_ordered_subsequence() -> None:
    actual = [
        ("@Human", "@Manager"),
        ("@Manager", "@WebIngest"),
        ("@WebIngest", "@Manager"),
        ("@Manager", "@Human"),
    ]

    assert _is_ordered_subsequence(
        [
            ("@Human", "@Manager"),
            ("@Manager", "@WebIngest"),
            ("@Manager", "@Human"),
        ],
        actual,
    )


def test_route_rejects_wrong_order() -> None:
    assert not _is_ordered_subsequence(
        [("@Manager", "@WebIngest"), ("@Human", "@Manager")],
        [("@Human", "@Manager"), ("@Manager", "@WebIngest")],
    )


def test_argument_match_normalizes_trailing_slash_inside_list() -> None:
    assert _contains_expected(
        ["https://coenradie.com/about/"],
        "https://coenradie.com/about",
    )


def test_wrong_route_fails_route_evaluator() -> None:
    output = _output(
        messages=[
            MessageRecord(
                sender="@Human",
                recipient="@Manager",
                message_type="AgentMessage",
                content="question",
            ),
            MessageRecord(
                sender="@Manager",
                recipient="@Human",
                message_type="AgentMessage",
                content="answer",
            ),
        ]
    )
    evaluator = FollowedMessageRoute(
        expected_route=(
            ("@Human", "@Manager"),
            ("@Manager", "@Knowledge"),
            ("@Knowledge", "@Manager"),
            ("@Manager", "@Human"),
        )
    )

    result = evaluator.evaluate(_context(output))

    assert not result.value


def test_broken_fixture_answer_fails_required_terms() -> None:
    output = _output(human_responses=["No results found."])
    evaluator = HumanResponseContainsTerms(
        response_index=0,
        required_terms=("software architect",),
    )

    result = evaluator.evaluate(_context(output))

    assert not result.value


def test_answer_can_match_one_of_multiple_accepted_terms() -> None:
    output = _output(
        human_responses=["The knowledge base doesn't specify that fact; please ingest a source."]
    )
    evaluator = HumanResponseContainsAnyTerm(
        response_index=0,
        accepted_terms=("no information", "doesn't specify"),
    )

    result = evaluator.evaluate(_context(output))

    assert result.value


def test_forbidden_ingestion_call_fails_retrieval_only_evaluator() -> None:
    output = _output(
        tool_calls=[
            ToolCallRecord(
                run_id="run-1",
                tool_name="web_fetch_tool",
                tool_call_id="call-1",
                arguments_raw="{}",
                arguments={},
            )
        ]
    )
    evaluator = DidNotCallTools(forbidden_tools=("web_fetch_tool", "update_graph"))

    result = evaluator.evaluate(_context(output))

    assert not result["did_not_call_web_fetch_tool"].value
    assert result["did_not_call_update_graph"].value


def test_tool_success_distinguishes_failed_return_from_missing_return() -> None:
    call = ToolCallRecord(
        run_id="run-1",
        tool_name="search_graph",
        tool_call_id="call-1",
        arguments_raw="{}",
        arguments={},
    )
    output = _output(
        tool_calls=[call],
        tool_returns=[
            ToolReturnRecord(
                run_id="run-1",
                tool_name="search_graph",
                tool_call_id="call-1",
                success=False,
            )
        ],
    )

    result = ToolCallsSucceeded(tool_names=("search_graph",)).evaluate(_context(output))

    assert not result["tool_calls_succeeded"]


def _output(
    *,
    messages: list[MessageRecord] | None = None,
    human_responses: list[str] | None = None,
    tool_calls: list[ToolCallRecord] | None = None,
    tool_returns: list[ToolReturnRecord] | None = None,
) -> TeamCaseOutput:
    responses = human_responses or []
    return TeamCaseOutput(
        final_response=responses[-1] if responses else None,
        human_responses=responses,
        completion_reason="human_response",
        messages=messages or [],
        tool_calls=tool_calls or [],
        tool_returns=tool_returns or [],
        errors=[],
    )


def _context(output: TeamCaseOutput) -> Any:
    return cast(Any, SimpleNamespace(output=output))
