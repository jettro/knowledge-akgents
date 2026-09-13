"""Load project JSON definitions into Pydantic Evals datasets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator

from evals.evaluators.events import (
    CalledRequiredTools,
    CompletedSuccessfully,
    DidNotCallTools,
    FollowedMessageRoute,
    HumanResponseContainsAnyTerm,
    HumanResponseContainsTerms,
    ToolCallCount,
    ToolCallsSucceeded,
)
from evals.harness.fixture_knowledge import KnowledgeFixture
from evals.harness.models import TeamCaseInput, TeamCaseOutput

RETRIEVAL_ROUTE = (
    ("@Human", "@Manager"),
    ("@Manager", "@Knowledge"),
    ("@Knowledge", "@Manager"),
    ("@Manager", "@Human"),
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HumanResponseContainsTermsDefinition(StrictModel):
    type: Literal["human_response_contains_terms"]
    response_index: int = Field(default=0, ge=0)
    required_terms: tuple[str, ...] = Field(min_length=1)


class HumanResponseContainsAnyTermDefinition(StrictModel):
    type: Literal["human_response_contains_any_term"]
    response_index: int = Field(default=0, ge=0)
    accepted_terms: tuple[str, ...] | None = None
    accepted_terms_ref: str | None = None

    @model_validator(mode="after")
    def validate_term_source(self) -> HumanResponseContainsAnyTermDefinition:
        if (self.accepted_terms is None) == (self.accepted_terms_ref is None):
            raise ValueError("Provide exactly one of accepted_terms or accepted_terms_ref")
        if self.accepted_terms is not None and not self.accepted_terms:
            raise ValueError("accepted_terms must not be empty")
        return self


class ToolCallCountDefinition(StrictModel):
    type: Literal["tool_call_count"]
    tool_name: str = Field(min_length=1)
    minimum: int = Field(ge=0)
    maximum: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> ToolCallCountDefinition:
        if self.maximum is not None and self.maximum < self.minimum:
            raise ValueError("maximum must be greater than or equal to minimum")
        return self


EvaluatorDefinition = Annotated[
    HumanResponseContainsTermsDefinition
    | HumanResponseContainsAnyTermDefinition
    | ToolCallCountDefinition,
    Field(discriminator="type"),
]


class CaseDefinition(StrictModel):
    name: str = Field(min_length=1)
    message: str = Field(min_length=1)
    fixture: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    evaluators: tuple[EvaluatorDefinition, ...] = ()


class JsonDatasetDefinition(StrictModel):
    version: Literal[1]
    task: Literal["retrieval"]
    name: str = Field(min_length=1)
    default_fixture: str = Field(min_length=1)
    default_metadata: dict[str, str] = Field(default_factory=dict)
    vocabularies: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    fixtures: dict[str, KnowledgeFixture] = Field(min_length=1)
    cases: tuple[CaseDefinition, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dataset(self) -> JsonDatasetDefinition:
        names = [case.name for case in self.cases]
        if len(names) != len(set(names)):
            raise ValueError("Case names must be unique")
        if self.default_fixture not in self.fixtures:
            raise ValueError(f"Unknown default fixture {self.default_fixture!r}")
        for name, terms in self.vocabularies.items():
            if not terms:
                raise ValueError(f"Vocabulary {name!r} must not be empty")
        for case in self.cases:
            if case.fixture is not None and case.fixture not in self.fixtures:
                raise ValueError(
                    f"Case {case.name!r} references unknown fixture {case.fixture!r}"
                )
            for evaluator in case.evaluators:
                if (
                    isinstance(evaluator, HumanResponseContainsAnyTermDefinition)
                    and evaluator.accepted_terms_ref is not None
                    and evaluator.accepted_terms_ref not in self.vocabularies
                ):
                    raise ValueError(
                        f"Case {case.name!r} references unknown vocabulary "
                        f"{evaluator.accepted_terms_ref!r}"
                    )
        return self


def load_dataset_definition(path: Path) -> JsonDatasetDefinition:
    """Load one strictly validated project dataset definition."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load evaluation dataset JSON {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"Evaluation dataset JSON {path} must contain an object")
    return JsonDatasetDefinition.model_validate(raw)


def build_json_dataset(
    path: Path,
    timeout_seconds: float = 180.0,
) -> Dataset[TeamCaseInput, TeamCaseOutput, dict[str, Any]]:
    """Build a Pydantic Evals retrieval Dataset from one project JSON file."""
    definition = load_dataset_definition(path)
    cases: list[Case[TeamCaseInput, TeamCaseOutput, dict[str, Any]]] = []
    for case_definition in definition.cases:
        fixture_name = case_definition.fixture or definition.default_fixture
        metadata = {
            **definition.default_metadata,
            **case_definition.metadata,
            "fixture": fixture_name,
        }
        cases.append(
            Case(
                name=case_definition.name,
                inputs=TeamCaseInput(
                    message=case_definition.message,
                    timeout_seconds=timeout_seconds,
                    knowledge_fixture=definition.fixtures[fixture_name],
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


def build_case_evaluator(
    definition: EvaluatorDefinition,
    vocabularies: dict[str, tuple[str, ...]],
) -> Evaluator[Any, Any, Any]:
    """Convert one allow-listed JSON evaluator definition to Python logic."""
    if isinstance(definition, HumanResponseContainsTermsDefinition):
        return HumanResponseContainsTerms(
            response_index=definition.response_index,
            required_terms=definition.required_terms,
        )
    if isinstance(definition, HumanResponseContainsAnyTermDefinition):
        terms = (
            definition.accepted_terms
            if definition.accepted_terms is not None
            else vocabularies[definition.accepted_terms_ref or ""]
        )
        return HumanResponseContainsAnyTerm(
            response_index=definition.response_index,
            accepted_terms=terms,
        )
    if isinstance(definition, ToolCallCountDefinition):
        return ToolCallCount(
            tool_name=definition.tool_name,
            minimum=definition.minimum,
            maximum=definition.maximum,
        )
    raise TypeError(f"Unsupported evaluator definition: {type(definition).__name__}")
