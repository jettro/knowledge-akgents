"""Executable combined Jettro and Yuma production end-to-end scenarios."""

from __future__ import annotations

from typing import Any

from pydantic_evals import Dataset

from akgentic_evals.datasets import combine_datasets
from akgentic_evals.models import AkgenticCaseOutput
from evals.harness.models import KnowledgeCaseInput
from evals.scenarios.jettro_scenario import build_jettro_scenario_dataset
from evals.scenarios.yuma_scenario import build_yuma_scenario_dataset


def build_production_e2e_dataset(
    timeout_seconds: float = 180.0,
) -> Dataset[KnowledgeCaseInput, AkgenticCaseOutput, dict[str, Any]]:
    """Combine both scenarios while retaining their case-specific evaluators."""
    datasets = (
        build_jettro_scenario_dataset(timeout_seconds),
        build_yuma_scenario_dataset(timeout_seconds),
    )
    return combine_datasets(
        name="knowledge-akgents/production-end-to-end",
        datasets=datasets,
        metadata={"mode": "production-live-multi-turn"},
    )
