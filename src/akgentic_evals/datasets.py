"""Allow-listed dataset definitions for reusable deterministic evaluators."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator

from akgentic_evals.evaluators import (
    HumanResponseContainsAnyTerm,
    HumanResponseContainsTerms,
    ToolCallCount,
    ToolEvidenceContainsTerms,
)


class StrictDefinitionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class HumanResponseContainsTermsDefinition(StrictDefinitionModel):
    type: Literal["human_response_contains_terms"]
    response_index: int = Field(default=0, ge=0)
    required_terms: tuple[str, ...] = Field(min_length=1)


class HumanResponseContainsAnyTermDefinition(StrictDefinitionModel):
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


class ToolCallCountDefinition(StrictDefinitionModel):
    type: Literal["tool_call_count"]
    tool_name: str = Field(min_length=1)
    minimum: int = Field(ge=0)
    maximum: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> ToolCallCountDefinition:
        if self.maximum is not None and self.maximum < self.minimum:
            raise ValueError("maximum must be greater than or equal to minimum")
        return self


class ToolEvidenceContainsTermsDefinition(StrictDefinitionModel):
    type: Literal["tool_evidence_contains_terms"]
    tool_name: str = Field(min_length=1)
    required_terms: tuple[str, ...] = Field(min_length=1)


EvaluatorDefinition = Annotated[
    HumanResponseContainsTermsDefinition
    | HumanResponseContainsAnyTermDefinition
    | ToolCallCountDefinition
    | ToolEvidenceContainsTermsDefinition,
    Field(discriminator="type"),
]


def build_evaluator(
    definition: EvaluatorDefinition,
    vocabularies: dict[str, tuple[str, ...]],
) -> Evaluator[Any, Any, Any]:
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
    if isinstance(definition, ToolEvidenceContainsTermsDefinition):
        return ToolEvidenceContainsTerms(
            tool_name=definition.tool_name,
            required_terms=definition.required_terms,
        )
    raise TypeError(f"Unsupported evaluator definition: {type(definition).__name__}")


def combine_datasets[InputsT, OutputT](
    name: str,
    datasets: Sequence[Dataset[InputsT, OutputT, dict[str, Any]]],
    *,
    metadata: Mapping[str, Any] | None = None,
) -> Dataset[InputsT, OutputT, dict[str, Any]]:
    """Flatten datasets while preserving their shared evaluators on each case."""
    metadata_update = dict(metadata or {})
    cases: list[Case[InputsT, OutputT, dict[str, Any]]] = []
    report_evaluators = []
    for dataset in datasets:
        report_evaluators.extend(dataset.report_evaluators)
        for case in dataset.cases:
            cases.append(
                Case(
                    name=case.name,
                    inputs=case.inputs,
                    metadata={**(case.metadata or {}), **metadata_update},
                    expected_output=case.expected_output,
                    evaluators=tuple(dataset.evaluators) + tuple(case.evaluators),
                )
            )
    return Dataset(
        name=name,
        cases=cases,
        report_evaluators=report_evaluators,
    )


class UnknownCaseError(ValueError):
    """Raised when a requested case does not exist in a dataset."""


def select_case(
    dataset: Dataset[Any, Any, Any],
    case_name: str | None,
) -> None:
    """Restrict a dataset to one named case."""
    if case_name is None:
        return
    selected = [case for case in dataset.cases if case.name == case_name]
    if not selected:
        available = ", ".join(case.name or "<unnamed>" for case in dataset.cases)
        raise UnknownCaseError(
            f"Unknown case {case_name!r}. Available cases: {available}"
        )
    dataset.cases[:] = selected
