"""Compatibility wrapper for the built-in retrieval JSON dataset."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic_evals import Dataset

from evals.harness.dataset_loader import (
    build_json_dataset,
    load_dataset_definition,
)
from evals.harness.models import TeamCaseInput, TeamCaseOutput

DATASET_PATH = Path(__file__).parents[1] / "datasets" / "retrieval_only.json"

_DEFAULT_DEFINITION = load_dataset_definition(DATASET_PATH)
MISSING_KNOWLEDGE_TERMS = _DEFAULT_DEFINITION.vocabularies["missing_knowledge"]


def build_retrieval_only_dataset(
    timeout_seconds: float = 180.0,
) -> Dataset[TeamCaseInput, TeamCaseOutput, dict[str, Any]]:
    return build_json_dataset(
        DATASET_PATH,
        timeout_seconds=timeout_seconds,
    ).dataset
