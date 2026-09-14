"""Dataset-shape tests for the combined production end-to-end run."""

from __future__ import annotations

from evals.scenarios.production_e2e import build_production_e2e_dataset


def test_production_e2e_dataset_combines_jettro_and_yuma() -> None:
    dataset = build_production_e2e_dataset(timeout_seconds=1)

    assert dataset.name == "knowledge-akgents/production-end-to-end"
    assert [case.name for case in dataset.cases] == [
        "ingest-and-query-jettro-about",
        "ingest-and-query-yuma-background",
    ]
    assert all(len(case.inputs.ordered_turns()) == 3 for case in dataset.cases)
    assert all(case.evaluators for case in dataset.cases)
    assert all(case.metadata["mode"] == "production-live-multi-turn" for case in dataset.cases)
    assert dataset.evaluators == []
