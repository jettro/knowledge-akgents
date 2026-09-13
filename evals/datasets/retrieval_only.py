"""Retrieval-only cases backed by a reviewed knowledge fixture."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic_evals import Case, Dataset

from evals.event_evaluators import (
    CalledRequiredTools,
    CompletedSuccessfully,
    DidNotCallTools,
    FollowedMessageRoute,
    HumanResponseContainsAnyTerm,
    HumanResponseContainsTerms,
    ToolCallCount,
    ToolCallsSucceeded,
)
from evals.models import TeamCaseInput, TeamCaseOutput

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "pilot_knowledge.json"
RETRIEVAL_ROUTE = (
    ("@Human", "@Manager"),
    ("@Manager", "@Knowledge"),
    ("@Knowledge", "@Manager"),
    ("@Manager", "@Human"),
)
MISSING_KNOWLEDGE_TERMS = (
    "not in the knowledge base",
    "does not contain",
    "doesn't contain",
    "does not specify",
    "doesn't specify",
    "doesn’t specify",
    "does not state",
    "doesn't state",
    "doesn’t state",
    "not present",
    "no information",
    "not available",
    "nothing relevant",
)


def build_retrieval_only_dataset(
    timeout_seconds: float = 180.0,
) -> Dataset[TeamCaseInput, TeamCaseOutput, dict[str, Any]]:
    fixture_path = str(FIXTURE_PATH)
    return Dataset(
        name="knowledge-akgents/pilot-retrieval-only",
        cases=[
            _case(
                "jettro-profession",
                "What is the profession of Jettro Coenradie?",
                ("software architect",),
                fixture_path,
                timeout_seconds,
                "canonical",
            ),
            _case(
                "jettro-profession-paraphrase",
                "Which job does Jettro Coenradie have?",
                ("software architect",),
                fixture_path,
                timeout_seconds,
                "paraphrase",
            ),
            _case(
                "jettro-surname",
                "What is the last name of Jettro?",
                ("Coenradie",),
                fixture_path,
                timeout_seconds,
                "canonical",
            ),
            _case(
                "jettro-surname-paraphrase",
                "Can you tell me Jettro's family name?",
                ("Coenradie",),
                fixture_path,
                timeout_seconds,
                "paraphrase",
            ),
            _case(
                "yuma-purpose",
                "What does Yuma do?",
                ("digital", "transformation", "partner"),
                fixture_path,
                timeout_seconds,
                "canonical",
            ),
            _case(
                "yuma-purpose-paraphrase",
                "How does Yuma help organizations with digital work?",
                ("digital", "transformation", "partner"),
                fixture_path,
                timeout_seconds,
                "paraphrase",
            ),
            _case(
                "yuma-companies",
                "What companies formed Yuma?",
                (
                    "xplus",
                    "Luminis",
                    "BPSOLUTIONS",
                    "Total Design",
                    "Aprico",
                    "B12 Consulting",
                ),
                fixture_path,
                timeout_seconds,
                "canonical",
            ),
            _case(
                "yuma-companies-paraphrase",
                "Name the businesses that came together to create Yuma.",
                (
                    "xplus",
                    "Luminis",
                    "BPSOLUTIONS",
                    "Total Design",
                    "Aprico",
                    "B12 Consulting",
                ),
                fixture_path,
                timeout_seconds,
                "paraphrase",
            ),
            _case(
                "jettro-profession-and-yuma-purpose",
                "What is Jettro Coenradie's profession, and what does Yuma do?",
                ("software architect", "digital", "transformation", "partner"),
                fixture_path,
                timeout_seconds,
                "multi-entity",
            ),
            _case(
                "yuma-consulting-founders",
                "Which companies that formed Yuma have Consulting or Consultants in their name?",
                ("Aprico", "B12 Consulting"),
                fixture_path,
                timeout_seconds,
                "filtered-list",
            ),
            Case(
                name="jettro-unknown-favorite-database",
                inputs=TeamCaseInput(
                    message="What is Jettro Coenradie's favorite database?",
                    timeout_seconds=timeout_seconds,
                    knowledge_fixture_path=fixture_path,
                ),
                metadata={
                    "mode": "fixed-knowledge-retrieval-only",
                    "fixture_captured": "2026-09-12",
                    "prompt_variant": "negative-control",
                },
                evaluators=(
                    HumanResponseContainsAnyTerm(
                        response_index=0,
                        accepted_terms=MISSING_KNOWLEDGE_TERMS,
                    ),
                    HumanResponseContainsTerms(
                        response_index=0,
                        required_terms=("ingest",),
                    ),
                    ToolCallCount(tool_name="search_graph", minimum=1, maximum=2),
                ),
            ),
            Case(
                name="jettro-profession-and-unknown-favorite-database",
                inputs=TeamCaseInput(
                    message=(
                        "What is Jettro Coenradie's profession and what is his "
                        "favorite database?"
                    ),
                    timeout_seconds=timeout_seconds,
                    knowledge_fixture_path=fixture_path,
                ),
                metadata={
                    "mode": "fixed-knowledge-retrieval-only",
                    "fixture_captured": "2026-09-12",
                    "prompt_variant": "partial-knowledge-negative-control",
                },
                evaluators=(
                    HumanResponseContainsTerms(
                        response_index=0,
                        required_terms=("software architect", "ingest"),
                    ),
                    HumanResponseContainsAnyTerm(
                        response_index=0,
                        accepted_terms=MISSING_KNOWLEDGE_TERMS,
                    ),
                    ToolCallCount(tool_name="search_graph", minimum=1, maximum=3),
                ),
            ),
        ],
        evaluators=[
            CompletedSuccessfully(),
            FollowedMessageRoute(expected_route=RETRIEVAL_ROUTE),
            CalledRequiredTools(required_tools=("search_graph",)),
            DidNotCallTools(forbidden_tools=("web_fetch_tool", "update_graph")),
            ToolCallCount(tool_name="search_graph", minimum=1),
            ToolCallsSucceeded(tool_names=("search_graph",)),
        ],
    )


def _case(
    name: str,
    message: str,
    required_terms: tuple[str, ...],
    fixture_path: str,
    timeout_seconds: float,
    prompt_variant: str,
) -> Case[TeamCaseInput, TeamCaseOutput, dict[str, Any]]:
    return Case(
        name=name,
        inputs=TeamCaseInput(
            message=message,
            timeout_seconds=timeout_seconds,
            knowledge_fixture_path=fixture_path,
        ),
        metadata={
            "mode": "fixed-knowledge-retrieval-only",
            "fixture_captured": "2026-09-12",
            "prompt_variant": prompt_variant,
        },
        evaluators=(
            HumanResponseContainsTerms(
                response_index=0,
                required_terms=required_terms,
            ),
        ),
    )
