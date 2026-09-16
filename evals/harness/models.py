"""Knowledge-specific inputs and reusable outputs for evaluations."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from akgentic_evals.runtime import AkgenticCaseInput
from evals.harness.fixture_knowledge import KnowledgeFixture

__all__ = ["KnowledgeCaseInput", "KnowledgeEvaluationEnvironment"]


class KnowledgeEvaluationEnvironment(BaseModel):
    fixture_source_url: str | None = None
    fixture_path: str | None = None
    fixture_paths: list[str] = Field(default_factory=list)
    fixture_web_failure: str | None = None
    knowledge_fixture: KnowledgeFixture | None = None
    knowledge_fixture_path: str | None = None

    @model_validator(mode="after")
    def validate_knowledge_fixtures(self) -> KnowledgeEvaluationEnvironment:
        if self.knowledge_fixture is not None and self.knowledge_fixture_path is not None:
            raise ValueError("Provide either knowledge_fixture or knowledge_fixture_path")
        return self


class KnowledgeCaseInput(AkgenticCaseInput):
    environment: KnowledgeEvaluationEnvironment = Field(
        default_factory=KnowledgeEvaluationEnvironment
    )
