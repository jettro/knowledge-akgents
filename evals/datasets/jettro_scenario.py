"""End-to-end Jettro ingestion and retrieval scenario."""

from __future__ import annotations

from typing import Any

from pydantic_evals import Case, Dataset

from evals.datasets.jettro_ingestion import FIXTURE_PATH, JETTRO_ABOUT_URL
from evals.event_evaluators import (
    CalledRequiredTools,
    CompletedSuccessfully,
    FollowedMessageRoute,
    HumanResponseContainsTerms,
    ToolArgumentsContain,
    ToolCallCount,
    ToolCallsSucceeded,
)
from evals.models import TeamCaseInput, TeamCaseOutput, TeamTurn


def build_jettro_scenario_dataset(
    timeout_seconds: float = 180.0,
) -> Dataset[TeamCaseInput, TeamCaseOutput, dict[str, Any]]:
    return Dataset(
        name="knowledge-akgents/jettro-end-to-end",
        cases=[
            Case(
                name="ingest-and-query-jettro-about",
                inputs=TeamCaseInput(
                    turns=[
                        TeamTurn(
                            message=(
                                f"Ingest {JETTRO_ABOUT_URL} and focus on Jettro "
                                "Coenradie's profession and name."
                            )
                        ),
                        TeamTurn(message="What is the profession of Jettro Coenradie?"),
                        TeamTurn(message="What is the last name of Jettro?"),
                    ],
                    timeout_seconds=timeout_seconds,
                    fixture_source_url=JETTRO_ABOUT_URL,
                    fixture_path=str(FIXTURE_PATH),
                ),
                metadata={
                    "source_url": JETTRO_ABOUT_URL,
                    "fixture_captured": "2026-09-12",
                    "mode": "fixed-fixture-multi-turn",
                },
            )
        ],
        evaluators=[
            CompletedSuccessfully(expected_human_responses=3),
            FollowedMessageRoute(
                expected_route=(
                    ("@Human", "@Manager"),
                    ("@Manager", "@WebIngest"),
                    ("@WebIngest", "@Manager"),
                    ("@Manager", "@Human"),
                    ("@Human", "@Manager"),
                    ("@Manager", "@Knowledge"),
                    ("@Knowledge", "@Manager"),
                    ("@Manager", "@Human"),
                    ("@Human", "@Manager"),
                    ("@Manager", "@Knowledge"),
                    ("@Knowledge", "@Manager"),
                    ("@Manager", "@Human"),
                )
            ),
            CalledRequiredTools(required_tools=("web_fetch_tool", "update_graph", "search_graph")),
            ToolArgumentsContain(
                tool_name="web_fetch_tool",
                argument_name="urls",
                expected_value=JETTRO_ABOUT_URL,
            ),
            ToolCallCount(tool_name="web_fetch_tool", minimum=1, maximum=1),
            ToolCallCount(tool_name="update_graph", minimum=1, maximum=1),
            ToolCallCount(tool_name="search_graph", minimum=2),
            ToolCallsSucceeded(tool_names=("web_fetch_tool", "update_graph", "search_graph")),
            HumanResponseContainsTerms(
                response_index=1,
                required_terms=("software architect",),
            ),
            HumanResponseContainsTerms(
                response_index=2,
                required_terms=("Coenradie",),
            ),
        ],
    )
