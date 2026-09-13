"""Fixed-fixture scenarios for unchanged and forced URL ingestion."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic_evals import Case, Dataset

from evals.event_evaluators import (
    CalledRequiredTools,
    CompletedSuccessfully,
    FollowedMessageRoute,
    HumanResponseContainsAnyTerm,
    ToolArgumentsContain,
    ToolCallCount,
    ToolCallsInOrder,
    ToolCallsSucceeded,
)
from evals.models import TeamCaseInput, TeamCaseOutput, TeamTurn

CHANGE_AWARE_URL = "https://eval.invalid/project-beacon"
FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "change_aware_page.txt"
FIXTURE_V2_PATH = Path(__file__).parents[1] / "fixtures" / "change_aware_page_v2.txt"
TWO_INGESTION_ROUTES = (
    ("@Human", "@Manager"),
    ("@Manager", "@WebIngest"),
    ("@WebIngest", "@Manager"),
    ("@Manager", "@Human"),
    ("@Human", "@Manager"),
    ("@Manager", "@WebIngest"),
    ("@WebIngest", "@Manager"),
    ("@Manager", "@Human"),
)


def build_change_aware_ingestion_dataset(
    timeout_seconds: float = 180.0,
) -> Dataset[TeamCaseInput, TeamCaseOutput, dict[str, Any]]:
    return Dataset(
        name="knowledge-akgents/change-aware-ingestion",
        cases=[
            Case(
                name="skip-unchanged-page",
                inputs=TeamCaseInput(
                    turns=[
                        TeamTurn(message=f"Ingest {CHANGE_AWARE_URL}."),
                        TeamTurn(message=f"Ingest {CHANGE_AWARE_URL} again."),
                    ],
                    timeout_seconds=timeout_seconds,
                    fixture_source_url=CHANGE_AWARE_URL,
                    fixture_path=str(FIXTURE_PATH),
                ),
                metadata={
                    "source_url": CHANGE_AWARE_URL,
                    "fixture_kind": "synthetic-unchanged-content",
                    "mode": "fixed-fixture-multi-turn",
                },
                evaluators=(
                    ToolCallCount(tool_name="web_fetch_tool", minimum=2, maximum=2),
                    ToolCallCount(tool_name="update_graph", minimum=1, maximum=1),
                    ToolCallCount(tool_name="commit_web_ingestion", minimum=1, maximum=1),
                    ToolCallsInOrder(
                        expected_tools=(
                            "web_fetch_tool",
                            "update_graph",
                            "commit_web_ingestion",
                            "web_fetch_tool",
                        )
                    ),
                    HumanResponseContainsAnyTerm(
                        response_index=1,
                        accepted_terms=("unchanged", "no update", "nothing needed updating"),
                    ),
                ),
            ),
            Case(
                name="force-unchanged-page",
                inputs=TeamCaseInput(
                    turns=[
                        TeamTurn(message=f"Ingest {CHANGE_AWARE_URL}."),
                        TeamTurn(
                            message=(
                                f"Force re-ingest {CHANGE_AWARE_URL}, even if it is unchanged."
                            )
                        ),
                    ],
                    timeout_seconds=timeout_seconds,
                    fixture_source_url=CHANGE_AWARE_URL,
                    fixture_path=str(FIXTURE_PATH),
                ),
                metadata={
                    "source_url": CHANGE_AWARE_URL,
                    "fixture_kind": "synthetic-forced-content",
                    "mode": "fixed-fixture-multi-turn",
                },
                evaluators=(
                    ToolCallCount(tool_name="web_fetch_tool", minimum=2, maximum=2),
                    ToolArgumentsContain(
                        tool_name="web_fetch_tool",
                        argument_name="force",
                        expected_value=True,
                    ),
                    ToolCallCount(tool_name="update_graph", minimum=2, maximum=2),
                    ToolCallCount(tool_name="commit_web_ingestion", minimum=2, maximum=2),
                    ToolCallsInOrder(
                        expected_tools=(
                            "web_fetch_tool",
                            "update_graph",
                            "commit_web_ingestion",
                            "web_fetch_tool",
                            "update_graph",
                            "commit_web_ingestion",
                        )
                    ),
                ),
            ),
            Case(
                name="replace-changed-source-facts",
                inputs=TeamCaseInput(
                    turns=[
                        TeamTurn(message=f"Ingest {CHANGE_AWARE_URL}."),
                        TeamTurn(message=f"Ingest the changed {CHANGE_AWARE_URL} again."),
                    ],
                    timeout_seconds=timeout_seconds,
                    fixture_source_url=CHANGE_AWARE_URL,
                    fixture_paths=[str(FIXTURE_PATH), str(FIXTURE_V2_PATH)],
                ),
                metadata={
                    "source_url": CHANGE_AWARE_URL,
                    "fixture_kind": "synthetic-changed-content",
                    "mode": "fixed-fixture-multi-turn",
                },
                evaluators=(
                    ToolCallCount(tool_name="web_fetch_tool", minimum=2, maximum=2),
                    ToolCallCount(tool_name="update_graph", minimum=2, maximum=2),
                    ToolCallCount(tool_name="commit_web_ingestion", minimum=2, maximum=2),
                    ToolCallsInOrder(
                        expected_tools=(
                            "web_fetch_tool",
                            "update_graph",
                            "commit_web_ingestion",
                            "web_fetch_tool",
                            "update_graph",
                            "commit_web_ingestion",
                        )
                    ),
                    ToolArgumentsContain(
                        tool_name="update_graph",
                        argument_name="delete_entities",
                        expected_value="Inspection windows",
                    ),
                    ToolArgumentsContain(
                        tool_name="update_graph",
                        argument_name="delete_relations",
                        expected_value={
                            "from_entity": "Project Beacon",
                            "to_entity": "Inspection windows",
                            "relation_type": "coordinates",
                        },
                    ),
                    HumanResponseContainsAnyTerm(
                        response_index=1,
                        accepted_terms=("replaced", "removed", "updated", "changed"),
                    ),
                ),
            ),
        ],
        evaluators=[
            CompletedSuccessfully(expected_human_responses=2),
            FollowedMessageRoute(expected_route=TWO_INGESTION_ROUTES),
            CalledRequiredTools(
                required_tools=("web_fetch_tool", "update_graph", "commit_web_ingestion")
            ),
            ToolArgumentsContain(
                tool_name="web_fetch_tool",
                argument_name="urls",
                expected_value=CHANGE_AWARE_URL,
            ),
            ToolCallsSucceeded(
                tool_names=("web_fetch_tool", "update_graph", "commit_web_ingestion")
            ),
        ],
    )
