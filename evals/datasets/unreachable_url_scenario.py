"""Fixed-fixture ingestion scenario for a controlled web-fetch failure."""

from __future__ import annotations

from typing import Any

from pydantic_evals import Case, Dataset

from evals.event_evaluators import (
    CalledRequiredTools,
    CompletedSuccessfully,
    FollowedMessageRoute,
    HumanResponseContainsAnyTerm,
    ToolArgumentsContain,
    ToolCallCount,
    ToolCallsSucceeded,
    ToolEvidenceContainsTerms,
)
from evals.models import TeamCaseInput, TeamCaseOutput

UNREACHABLE_URL = "https://eval.invalid/unreachable"
FAILURE_MESSAGE = "Connection timed out while fetching the evaluation URL"


def build_unreachable_url_scenario_dataset(
    timeout_seconds: float = 180.0,
) -> Dataset[TeamCaseInput, TeamCaseOutput, dict[str, Any]]:
    return Dataset(
        name="knowledge-akgents/unreachable-url-ingestion",
        cases=[
            Case(
                name="report-web-fetch-failure-without-graph-update",
                inputs=TeamCaseInput(
                    message=f"Ingest {UNREACHABLE_URL}.",
                    timeout_seconds=timeout_seconds,
                    fixture_source_url=UNREACHABLE_URL,
                    fixture_web_failure=FAILURE_MESSAGE,
                ),
                metadata={
                    "source_url": UNREACHABLE_URL,
                    "fixture_kind": "synthetic-web-failure",
                    "mode": "fixed-fixture",
                },
            )
        ],
        evaluators=[
            CompletedSuccessfully(),
            FollowedMessageRoute(
                expected_route=(
                    ("@Human", "@Manager"),
                    ("@Manager", "@WebIngest"),
                    ("@WebIngest", "@Manager"),
                    ("@Manager", "@Human"),
                )
            ),
            CalledRequiredTools(required_tools=("web_fetch_tool",)),
            ToolArgumentsContain(
                tool_name="web_fetch_tool",
                argument_name="urls",
                expected_value=UNREACHABLE_URL,
            ),
            ToolCallCount(tool_name="web_fetch_tool", minimum=1, maximum=2),
            ToolCallCount(tool_name="update_graph", minimum=0, maximum=0),
            ToolCallsSucceeded(tool_names=("web_fetch_tool",)),
            ToolEvidenceContainsTerms(
                tool_name="web_fetch_tool",
                required_terms=("failed_results", FAILURE_MESSAGE),
            ),
            HumanResponseContainsAnyTerm(
                response_index=0,
                accepted_terms=(
                    "could not fetch",
                    "couldn't fetch",
                    "failed to fetch",
                    "unable to fetch",
                    "timed out",
                    "timeout",
                    "unreachable",
                ),
            ),
        ],
    )
