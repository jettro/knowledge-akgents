"""The built-in retrieval dataset loaded from one JSON fixture bundle."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic_evals import Dataset

from evals.fixture_datasets import (
    build_fixture_dataset,
    load_fixture_dataset_definition,
)
from evals.models import TeamCaseInput, TeamCaseOutput

EVALS_ROOT = Path(__file__).parents[1]
FIXTURE_DATASET_PATH = EVALS_ROOT / "fixtures" / "retrieval_only.json"

_DEFAULT_DEFINITION = load_fixture_dataset_definition(FIXTURE_DATASET_PATH)
MISSING_KNOWLEDGE_TERMS = _DEFAULT_DEFINITION.vocabularies["missing_knowledge"]


def build_retrieval_only_dataset(
    timeout_seconds: float = 180.0,
) -> Dataset[TeamCaseInput, TeamCaseOutput, dict[str, Any]]:
    return build_fixture_dataset(
        FIXTURE_DATASET_PATH,
        timeout_seconds=timeout_seconds,
    )
