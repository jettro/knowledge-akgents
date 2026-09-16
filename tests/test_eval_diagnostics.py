"""Tests for reusable evaluation diagnostics."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from akgentic_evals.diagnostics import OutputInventory, SpanInventory
from akgentic_evals.models import (
    AkgenticCaseOutput,
    ToolCallRecord,
    ToolReturnRecord,
)


def test_output_inventory_correlates_calls_by_run_and_call_id() -> None:
    output = _output(
        tool_calls=[
            ToolCallRecord(
                run_id="run-2",
                tool_name="search",
                tool_call_id="call-1",
                arguments_raw="{}",
                arguments={},
            )
        ],
        tool_returns=[
            ToolReturnRecord(
                run_id="run-1",
                tool_name="search",
                tool_call_id="call-1",
                success=True,
            )
        ],
    )

    metrics = OutputInventory().evaluate(_context(output))

    assert metrics["uncorrelated_tool_call_count"] == 1


def test_span_inventory_reports_unique_span_names() -> None:
    context = cast(
        Any,
        SimpleNamespace(
            output=_output(),
            span_tree=[
                SimpleNamespace(name="agent run"),
                SimpleNamespace(name="tool call"),
                SimpleNamespace(name="tool call"),
            ],
        ),
    )

    metrics = SpanInventory().evaluate(context)

    assert metrics == {
        "span_count": 3,
        "tool_span_count": 2,
        "span_names": "agent run | tool call",
    }


def _output(
    *,
    tool_calls: list[ToolCallRecord] | None = None,
    tool_returns: list[ToolReturnRecord] | None = None,
) -> AkgenticCaseOutput:
    return AkgenticCaseOutput(
        final_response=None,
        human_responses=[],
        completion_reason="timeout",
        messages=[],
        tool_calls=tool_calls or [],
        tool_returns=tool_returns or [],
        errors=[],
    )


def _context(output: AkgenticCaseOutput) -> Any:
    return cast(Any, SimpleNamespace(output=output, span_tree=[]))
