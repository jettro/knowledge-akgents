"""Validate project JSON definitions and build Pydantic Evals datasets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator
from pydantic_evals import Case, Dataset

from akgentic_evals.datasets import (
    EvaluatorDefinition,
    HumanResponseContainsAnyTermDefinition,
    StrictDefinitionModel,
    build_evaluator,
)
from akgentic_evals.evaluators import (
    CalledRequiredTools,
    CompletedSuccessfully,
    DidNotCallTools,
    FollowedMessageRoute,
    ToolCallCount,
    ToolCallsSucceeded,
)
from akgentic_evals.models import AkgenticCaseOutput
from evals.harness.fixture_knowledge import KnowledgeFixture
from evals.harness.models import (
    KnowledgeCaseInput,
    KnowledgeEvaluationEnvironment,
)
from evals.routes import managed_route

RETRIEVAL_DATASET_PATH = (
    Path(__file__).parents[1] / "datasets" / "retrieval_only.json"
)


class CaseDefinition(StrictDefinitionModel):
    name: str = Field(min_length=1)
    message: str = Field(min_length=1)
    fixture: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    evaluators: tuple[EvaluatorDefinition, ...] = ()


class FixtureKnowledgeDefinition(StrictDefinitionModel):
    source: Literal["fixtures"]
    default_fixture: str = Field(min_length=1)
    fixtures: dict[str, KnowledgeFixture] = Field(min_length=1)


class RunningSystemKnowledgeDefinition(StrictDefinitionModel):
    source: Literal["running_system"]


KnowledgeDefinition = Annotated[
    FixtureKnowledgeDefinition | RunningSystemKnowledgeDefinition,
    Field(discriminator="source"),
]


class JsonDatasetDefinition(StrictDefinitionModel):
    schema_url: str | None = Field(default=None, alias="$schema")
    version: Literal[2]
    task: Literal["retrieval"]
    name: str = Field(min_length=1)
    knowledge: KnowledgeDefinition
    default_metadata: dict[str, str] = Field(default_factory=dict)
    vocabularies: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    cases: tuple[CaseDefinition, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dataset(self) -> JsonDatasetDefinition:
        names = [case.name for case in self.cases]
        if len(names) != len(set(names)):
            raise ValueError("Case names must be unique")
        fixture_names: set[str] = set()
        if isinstance(self.knowledge, FixtureKnowledgeDefinition):
            fixture_names = set(self.knowledge.fixtures)
            if self.knowledge.default_fixture not in fixture_names:
                raise ValueError(
                    f"Unknown default fixture {self.knowledge.default_fixture!r}"
                )
        for name, terms in self.vocabularies.items():
            if not terms:
                raise ValueError(f"Vocabulary {name!r} must not be empty")
        for case in self.cases:
            if case.fixture is not None and not fixture_names:
                raise ValueError(
                    f"Case {case.name!r} cannot select a fixture when knowledge.source "
                    "is 'running_system'"
                )
            if case.fixture is not None and case.fixture not in fixture_names:
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


@dataclass(frozen=True, slots=True)
class LoadedJsonDataset:
    dataset: Dataset[KnowledgeCaseInput, AkgenticCaseOutput, dict[str, Any]]
    execution_target: Literal["local_evaluation_team", "running_system"]


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
) -> LoadedJsonDataset:
    """Build a Pydantic Evals retrieval Dataset from one project JSON file."""
    definition = load_dataset_definition(path)
    fixture_definition = (
        definition.knowledge
        if isinstance(definition.knowledge, FixtureKnowledgeDefinition)
        else None
    )
    cases: list[Case[KnowledgeCaseInput, AkgenticCaseOutput, dict[str, Any]]] = []
    for case_definition in definition.cases:
        fixture_name = None
        knowledge_fixture = None
        if fixture_definition is not None:
            fixture_name = case_definition.fixture or fixture_definition.default_fixture
            knowledge_fixture = fixture_definition.fixtures[fixture_name]
        metadata = {
            **definition.default_metadata,
            **case_definition.metadata,
            "knowledge_source": definition.knowledge.source,
        }
        if fixture_name is not None:
            metadata["fixture"] = fixture_name
        cases.append(
            Case(
                name=case_definition.name,
                inputs=KnowledgeCaseInput(
                    message=case_definition.message,
                    timeout_seconds=timeout_seconds,
                    environment=KnowledgeEvaluationEnvironment(
                        knowledge_fixture=knowledge_fixture
                    ),
                ),
                metadata=metadata,
                evaluators=tuple(
                    build_evaluator(evaluator, definition.vocabularies)
                    for evaluator in case_definition.evaluators
                ),
            )
        )

    return LoadedJsonDataset(
        dataset=Dataset(
            name=definition.name,
            cases=cases,
            evaluators=[
                CompletedSuccessfully(),
                FollowedMessageRoute(expected_route=managed_route("@Knowledge")),
                CalledRequiredTools(required_tools=("search_graph",)),
                DidNotCallTools(forbidden_tools=("web_fetch_tool", "update_graph")),
                ToolCallCount(tool_name="search_graph", minimum=1),
                ToolCallsSucceeded(tool_names=("search_graph",)),
            ],
        ),
        execution_target=(
            "local_evaluation_team"
            if fixture_definition is not None
            else "running_system"
        ),
    )
