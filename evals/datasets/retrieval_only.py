"""Retrieval-only cases loaded from validated contributor-authored YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic_evals import Case, Dataset

from evals.event_evaluators import (
    CalledRequiredTools,
    CompletedSuccessfully,
    DidNotCallTools,
    FollowedMessageRoute,
    ToolCallCount,
    ToolCallsSucceeded,
)
from evals.models import TeamCaseInput, TeamCaseOutput
from evals.yaml_cases import build_case_evaluator, load_dataset_definition, resolve_case_path

EVALS_ROOT = Path(__file__).parents[1]
DEFINITIONS_PATH = EVALS_ROOT / "cases" / "retrieval_only.yaml"
FIXTURE_PATH = EVALS_ROOT / "fixtures" / "pilot_knowledge.json"
CONFLICT_FIXTURE_PATH = EVALS_ROOT / "fixtures" / "conflicting_knowledge.json"
RETRIEVAL_ROUTE = (
    ("@Human", "@Manager"),
    ("@Manager", "@Knowledge"),
    ("@Knowledge", "@Manager"),
    ("@Manager", "@Human"),
)

_DEFAULT_DEFINITION = load_dataset_definition(DEFINITIONS_PATH)
MISSING_KNOWLEDGE_TERMS = _DEFAULT_DEFINITION.vocabularies["missing_knowledge"]


def build_retrieval_only_dataset(
    timeout_seconds: float = 180.0,
    definitions_path: Path = DEFINITIONS_PATH,
) -> Dataset[TeamCaseInput, TeamCaseOutput, dict[str, Any]]:
    definition = load_dataset_definition(definitions_path)
    cases: list[Case[TeamCaseInput, TeamCaseOutput, dict[str, Any]]] = []
    for case_definition in definition.cases:
        fixture_value = case_definition.fixture or definition.default_fixture
        if fixture_value is None:
            raise ValueError(f"Case {case_definition.name!r} has no knowledge fixture")
        fixture_path = resolve_case_path(definitions_path, fixture_value, EVALS_ROOT)
        metadata = {**definition.default_metadata, **case_definition.metadata}
        cases.append(
            Case(
                name=case_definition.name,
                inputs=TeamCaseInput(
                    message=case_definition.message,
                    timeout_seconds=timeout_seconds,
                    knowledge_fixture_path=str(fixture_path),
                ),
                metadata=metadata,
                evaluators=tuple(
                    build_case_evaluator(evaluator, definition.vocabularies)
                    for evaluator in case_definition.evaluators
                ),
            )
        )

    return Dataset(
        name=definition.name,
        cases=cases,
        evaluators=[
            CompletedSuccessfully(),
            FollowedMessageRoute(expected_route=RETRIEVAL_ROUTE),
            CalledRequiredTools(required_tools=("search_graph",)),
            DidNotCallTools(forbidden_tools=("web_fetch_tool", "update_graph")),
            ToolCallCount(tool_name="search_graph", minimum=1),
            ToolCallsSucceeded(tool_names=("search_graph",)),
        ],
    )
