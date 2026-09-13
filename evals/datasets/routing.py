"""Routing cases for manager and direct-specialist behavior."""

from __future__ import annotations

from typing import Any

from pydantic_evals import Case, Dataset

from evals.datasets.jettro_ingestion import FIXTURE_PATH as JETTRO_FIXTURE_PATH
from evals.datasets.jettro_ingestion import JETTRO_ABOUT_URL
from evals.datasets.retrieval_only import FIXTURE_PATH as KNOWLEDGE_FIXTURE_PATH
from evals.event_evaluators import (
    CalledRequiredTools,
    CompletedSuccessfully,
    DidNotCallTools,
    DidNotInvolveActors,
    FollowedMessageRoute,
    HumanResponseContainsTerms,
    ToolArgumentsContain,
    ToolCallCount,
    ToolCallsSucceeded,
)
from evals.models import TeamCaseInput, TeamCaseOutput


def build_routing_dataset(
    timeout_seconds: float = 180.0,
) -> Dataset[TeamCaseInput, TeamCaseOutput, dict[str, Any]]:
    return Dataset(
        name="knowledge-akgents/routing",
        cases=[
            Case(
                name="direct-knowledge-bypasses-manager",
                inputs=TeamCaseInput(
                    message="What is the profession of Jettro Coenradie?",
                    target="@Knowledge",
                    timeout_seconds=timeout_seconds,
                    knowledge_fixture_path=str(KNOWLEDGE_FIXTURE_PATH),
                ),
                metadata={"route_kind": "direct-knowledge"},
                evaluators=(
                    FollowedMessageRoute(
                        expected_route=(
                            ("@Human", "@Knowledge"),
                            ("@Knowledge", "@Human"),
                        )
                    ),
                    DidNotInvolveActors(actor_names=("@Manager", "@WebIngest")),
                    CalledRequiredTools(required_tools=("search_graph",)),
                    DidNotCallTools(forbidden_tools=("web_fetch_tool", "update_graph")),
                    ToolCallsSucceeded(tool_names=("search_graph",)),
                    HumanResponseContainsTerms(
                        response_index=0,
                        required_terms=("software architect",),
                    ),
                ),
            ),
            Case(
                name="direct-web-ingest-bypasses-manager",
                inputs=TeamCaseInput(
                    message=(
                        f"Ingest {JETTRO_ABOUT_URL} and focus on Jettro Coenradie's "
                        "profession."
                    ),
                    target="@WebIngest",
                    timeout_seconds=timeout_seconds,
                    fixture_source_url=JETTRO_ABOUT_URL,
                    fixture_path=str(JETTRO_FIXTURE_PATH),
                ),
                metadata={"route_kind": "direct-web-ingest"},
                evaluators=(
                    FollowedMessageRoute(
                        expected_route=(
                            ("@Human", "@WebIngest"),
                            ("@WebIngest", "@Human"),
                        )
                    ),
                    DidNotInvolveActors(actor_names=("@Manager", "@Knowledge")),
                    CalledRequiredTools(required_tools=("web_fetch_tool", "update_graph")),
                    ToolArgumentsContain(
                        tool_name="web_fetch_tool",
                        argument_name="urls",
                        expected_value=JETTRO_ABOUT_URL,
                    ),
                    ToolCallsSucceeded(tool_names=("web_fetch_tool", "update_graph")),
                    HumanResponseContainsTerms(
                        response_index=0,
                        required_terms=("Jettro Coenradie", "software architect"),
                    ),
                ),
            ),
            Case(
                name="read-only-question-with-url-routes-to-knowledge",
                inputs=TeamCaseInput(
                    message=(
                        "Using only the stored knowledge, what does Yuma do? "
                        f"Do not ingest this source URL: {JETTRO_ABOUT_URL}"
                    ),
                    timeout_seconds=timeout_seconds,
                    fixture_source_url=JETTRO_ABOUT_URL,
                    fixture_path=str(JETTRO_FIXTURE_PATH),
                    knowledge_fixture_path=str(KNOWLEDGE_FIXTURE_PATH),
                ),
                metadata={"route_kind": "manager-read-only-url"},
                evaluators=(
                    FollowedMessageRoute(
                        expected_route=(
                            ("@Human", "@Manager"),
                            ("@Manager", "@Knowledge"),
                            ("@Knowledge", "@Manager"),
                            ("@Manager", "@Human"),
                        )
                    ),
                    DidNotInvolveActors(actor_names=("@WebIngest",)),
                    CalledRequiredTools(required_tools=("search_graph",)),
                    DidNotCallTools(forbidden_tools=("web_fetch_tool", "update_graph")),
                    ToolCallCount(tool_name="search_graph", minimum=1, maximum=2),
                    ToolCallsSucceeded(tool_names=("search_graph",)),
                    HumanResponseContainsTerms(
                        response_index=0,
                        required_terms=("digital", "transformation", "partner"),
                    ),
                ),
            ),
        ],
        evaluators=[CompletedSuccessfully()],
    )
