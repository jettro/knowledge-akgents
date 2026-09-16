"""Pydantic Evals task adapters for Knowledge Akgents."""

from __future__ import annotations

from akgentic_evals.models import AkgenticCaseOutput
from akgentic_evals.runtime import run_case_with_factory
from evals.harness.catalog import TeamCatalog
from evals.harness.models import KnowledgeCaseInput
from evals.harness.runtime import KnowledgeRuntimeFactory


def run_team_case(
    inputs: KnowledgeCaseInput,
    *,
    catalog_team: TeamCatalog = "evaluation",
) -> AkgenticCaseOutput:
    return run_case_with_factory(
        inputs,
        KnowledgeRuntimeFactory(catalog_team),
    )
