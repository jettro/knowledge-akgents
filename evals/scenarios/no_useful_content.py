"""Executable ingestion scenario for a page without useful knowledge."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic_evals import Case, Dataset

from evals.evaluators.events import (
    CalledRequiredTools,
    CompletedSuccessfully,
    FollowedMessageRoute,
    HumanResponseContainsAnyTerm,
    ToolArgumentsContain,
    ToolCallCount,
    ToolCallsSucceeded,
)
from evals.harness.models import TeamCaseInput, TeamCaseOutput

NO_USEFUL_CONTENT_URL = "https://eval.invalid/empty-content"
FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "no_useful_content_page.txt"


def build_no_useful_content_scenario_dataset(
    timeout_seconds: float = 180.0,
) -> Dataset[TeamCaseInput, TeamCaseOutput, dict[str, Any]]:
    return Dataset(
        name="knowledge-akgents/no-useful-content-ingestion",
        cases=[
            Case(
                name="skip-graph-update-for-boilerplate-only-page",
                inputs=TeamCaseInput(
                    message=f"Ingest {NO_USEFUL_CONTENT_URL}.",
                    timeout_seconds=timeout_seconds,
                    fixture_source_url=NO_USEFUL_CONTENT_URL,
                    fixture_path=str(FIXTURE_PATH),
                ),
                metadata={
                    "source_url": NO_USEFUL_CONTENT_URL,
                    "fixture_kind": "synthetic-boilerplate-only",
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
                expected_value=NO_USEFUL_CONTENT_URL,
            ),
            ToolCallCount(tool_name="web_fetch_tool", minimum=1, maximum=1),
            ToolCallCount(tool_name="update_graph", minimum=0, maximum=0),
            ToolCallsSucceeded(tool_names=("web_fetch_tool",)),
            HumanResponseContainsAnyTerm(
                response_index=0,
                accepted_terms=(
                    "no useful",
                    "no usable",
                    "nothing useful",
                    "nothing to store",
                    "could not identify",
                    "couldn't identify",
                    "no knowledge",
                    "no substantive",
                    "does not contain",
                    "doesn't contain",
                    "only contains",
                    "only includes",
                ),
            ),
        ],
    )
