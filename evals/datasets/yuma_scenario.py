"""End-to-end Yuma ingestion and retrieval scenario."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic_evals import Case, Dataset

from evals.event_evaluators import (
    CalledRequiredTools,
    CompletedSuccessfully,
    FollowedMessageRoute,
    HumanResponseContainsAnyTerm,
    HumanResponseContainsTerms,
    ToolArgumentsContain,
    ToolCallCount,
    ToolCallsSucceeded,
)
from evals.models import TeamCaseInput, TeamCaseOutput, TeamTurn

YUMA_BACKGROUND_URL = "https://www.weareyuma.com/en/about/about-us/background"
FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "yuma_background.txt"


def build_yuma_scenario_dataset(
    timeout_seconds: float = 180.0,
) -> Dataset[TeamCaseInput, TeamCaseOutput, dict[str, Any]]:
    return Dataset(
        name="knowledge-akgents/yuma-end-to-end",
        cases=[
            Case(
                name="ingest-and-query-yuma-background",
                inputs=TeamCaseInput(
                    turns=[
                        TeamTurn(
                            message=(
                                f"Ingest {YUMA_BACKGROUND_URL} and focus on what Yuma "
                                "does and which companies formed it."
                            )
                        ),
                        TeamTurn(message="What does Yuma do?"),
                        TeamTurn(message="What companies formed Yuma?"),
                    ],
                    timeout_seconds=timeout_seconds,
                    fixture_source_url=YUMA_BACKGROUND_URL,
                    fixture_path=str(FIXTURE_PATH),
                ),
                metadata={
                    "source_url": YUMA_BACKGROUND_URL,
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
                expected_value=YUMA_BACKGROUND_URL,
            ),
            ToolCallCount(tool_name="web_fetch_tool", minimum=1, maximum=1),
            ToolCallCount(tool_name="update_graph", minimum=1, maximum=1),
            ToolCallCount(tool_name="search_graph", minimum=2),
            ToolCallsSucceeded(tool_names=("web_fetch_tool", "update_graph", "search_graph")),
            HumanResponseContainsTerms(
                response_index=1,
                required_terms=("transformation", "partner"),
            ),
            HumanResponseContainsAnyTerm(
                response_index=1,
                accepted_terms=(
                    "AI transformation",
                    "AI-transformation",
                    "digital transformation",
                ),
            ),
            HumanResponseContainsTerms(
                response_index=2,
                required_terms=(
                    "xplus",
                    "Luminis",
                    "BPSOLUTIONS",
                    "Total Design",
                    "Aprico",
                    "B12 Consulting",
                ),
            ),
        ],
    )
