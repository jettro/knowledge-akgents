"""Validated YAML definitions for contributor-authored evaluation cases."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_evals.evaluators import Evaluator

from evals.event_evaluators import (
    HumanResponseContainsAnyTerm,
    HumanResponseContainsTerms,
    ToolCallCount,
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


class DatasetDefinition(StrictModel):
    version: Literal[1]
    name: str = Field(min_length=1)
    default_fixture: str | None = None
    default_metadata: dict[str, str] = Field(default_factory=dict)
    vocabularies: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    cases: tuple[CaseDefinition, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dataset(self) -> DatasetDefinition:
        names = [case.name for case in self.cases]
        if len(names) != len(set(names)):
            raise ValueError("Case names must be unique")
        for name, terms in self.vocabularies.items():
            if not terms:
                raise ValueError(f"Vocabulary {name!r} must not be empty")
        for case in self.cases:
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


def load_dataset_definition(path: Path) -> DatasetDefinition:
    """Load one strict YAML dataset definition."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Could not load evaluation YAML {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"Evaluation YAML {path} must contain a mapping at the top level")
    return DatasetDefinition.model_validate(raw)


def build_case_evaluator(
    definition: EvaluatorDefinition,
    vocabularies: dict[str, tuple[str, ...]],
) -> Evaluator[Any, Any, Any]:
    """Convert one allow-listed YAML evaluator definition to Python logic."""
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


def resolve_case_path(config_path: Path, value: str, allowed_root: Path) -> Path:
    """Resolve a YAML path while preventing reads outside the evaluation tree."""
    if Path(value).is_absolute():
        raise ValueError("Evaluation YAML paths must be relative")
    resolved = (config_path.parent / value).resolve()
    root = allowed_root.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"Evaluation YAML path escapes {root}: {value}")
    if not resolved.is_file():
        raise ValueError(f"Evaluation YAML path does not exist: {resolved}")
    return resolved
