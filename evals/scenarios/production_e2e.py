"""Executable combined Jettro and Yuma production end-to-end scenarios."""

from __future__ import annotations

from typing import Any

from pydantic_evals import Case, Dataset

from evals.harness.models import TeamCaseInput, TeamCaseOutput
from evals.scenarios.jettro_scenario import build_jettro_scenario_dataset
from evals.scenarios.yuma_scenario import build_yuma_scenario_dataset


def build_production_e2e_dataset(
    timeout_seconds: float = 180.0,
) -> Dataset[TeamCaseInput, TeamCaseOutput, dict[str, Any]]:
    """Combine both scenarios while retaining their case-specific evaluators."""
    datasets = (
        build_jettro_scenario_dataset(timeout_seconds),
        build_yuma_scenario_dataset(timeout_seconds),
    )
    cases: list[Case[TeamCaseInput, TeamCaseOutput, dict[str, Any]]] = []
    for dataset in datasets:
        for case in dataset.cases:
            metadata = {
                **(case.metadata or {}),
                "mode": "production-live-multi-turn",
            }
            cases.append(
                Case(
                    name=case.name,
                    inputs=case.inputs,
                    metadata=metadata,
                    expected_output=case.expected_output,
                    evaluators=tuple(dataset.evaluators) + tuple(case.evaluators),
                )
            )

    return Dataset(
        name="knowledge-akgents/production-end-to-end",
        cases=cases,
    )
