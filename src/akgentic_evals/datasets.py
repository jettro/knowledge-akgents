"""Allow-listed dataset definitions for reusable deterministic evaluators."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
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
    tool_name: str = Field(default="search_graph", min_length=1)
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
