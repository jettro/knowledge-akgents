"""Executable routing cases for manager and direct-specialist behavior."""

from __future__ import annotations

from typing import Any

from pydantic_evals import Case, Dataset

from akgentic_evals.evaluators import (
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
from akgentic_evals.models import AkgenticCaseOutput
from evals.harness.dataset_loader import (
    RETRIEVAL_DATASET_PATH,
    FixtureKnowledgeDefinition,
    load_dataset_definition,
)
from evals.harness.models import (
    KnowledgeCaseInput,
    KnowledgeEvaluationEnvironment,
)
from evals.routes import direct_route, managed_route
from evals.scenarios.jettro_ingestion import FIXTURE_PATH as JETTRO_FIXTURE_PATH
from evals.scenarios.jettro_ingestion import JETTRO_ABOUT_URL

_RETRIEVAL_DEFINITION = load_dataset_definition(RETRIEVAL_DATASET_PATH)
if not isinstance(_RETRIEVAL_DEFINITION.knowledge, FixtureKnowledgeDefinition):
    raise ValueError("The routing scenario requires fixture knowledge")
KNOWLEDGE_FIXTURE = _RETRIEVAL_DEFINITION.knowledge.fixtures["pilot"]


def build_routing_dataset(
    timeout_seconds: float = 180.0,
) -> Dataset[KnowledgeCaseInput, AkgenticCaseOutput, dict[str, Any]]:
    return Dataset(
        name="knowledge-akgents/routing",
        cases=[
            Case(
                name="direct-knowledge-bypasses-manager",
                inputs=KnowledgeCaseInput(
                    message="What is the profession of Jettro Coenradie?",
                    target="@Knowledge",
                    timeout_seconds=timeout_seconds,
                    environment=KnowledgeEvaluationEnvironment(
                        knowledge_fixture=KNOWLEDGE_FIXTURE
                    ),
                ),
                metadata={"route_kind": "direct-knowledge"},
                evaluators=(
                    FollowedMessageRoute(
                        expected_route=direct_route("@Knowledge")
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
                inputs=KnowledgeCaseInput(
                    message=(
                        f"Ingest {JETTRO_ABOUT_URL} and focus on Jettro Coenradie's "
                        "profession."
                    ),
                    target="@WebIngest",
                    timeout_seconds=timeout_seconds,
                    environment=KnowledgeEvaluationEnvironment(
                        fixture_source_url=JETTRO_ABOUT_URL,
                        fixture_path=str(JETTRO_FIXTURE_PATH),
                    ),
                ),
                metadata={"route_kind": "direct-web-ingest"},
                evaluators=(
                    FollowedMessageRoute(
                        expected_route=direct_route("@WebIngest")
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
                inputs=KnowledgeCaseInput(
                    message=(
                        "Using only the stored knowledge, what does Yuma do? "
                        f"Do not ingest this source URL: {JETTRO_ABOUT_URL}"
                    ),
                    timeout_seconds=timeout_seconds,
                    environment=KnowledgeEvaluationEnvironment(
                        fixture_source_url=JETTRO_ABOUT_URL,
                        fixture_path=str(JETTRO_FIXTURE_PATH),
                        knowledge_fixture=KNOWLEDGE_FIXTURE,
                    ),
                ),
                metadata={"route_kind": "manager-read-only-url"},
                evaluators=(
                    FollowedMessageRoute(
                        expected_route=managed_route("@Knowledge")
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
