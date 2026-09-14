"""Dataset-shape tests for change-aware ingestion scenarios."""

from __future__ import annotations

from evals.scenarios.change_aware_ingestion import (
    CHANGE_AWARE_URL,
    build_change_aware_ingestion_dataset,
)


def test_change_aware_dataset_defines_skip_force_and_replace_cases() -> None:
    dataset = build_change_aware_ingestion_dataset(timeout_seconds=42)

    assert dataset.name == "knowledge-akgents/change-aware-ingestion"
    assert [case.name for case in dataset.cases] == [
        "skip-unchanged-page",
        "force-unchanged-page",
        "replace-changed-source-facts",
    ]
    assert all(case.inputs.timeout_seconds == 42 for case in dataset.cases)
    assert all(case.inputs.fixture_source_url == CHANGE_AWARE_URL for case in dataset.cases)
    assert all(len(case.inputs.ordered_turns()) == 2 for case in dataset.cases)


def test_force_case_explicitly_requests_forced_reingestion() -> None:
    dataset = build_change_aware_ingestion_dataset()
    force_case = dataset.cases[1]

    assert "force" in force_case.inputs.ordered_turns()[1].message.casefold()
    assert "unchanged" in force_case.inputs.ordered_turns()[1].message.casefold()


def test_changed_case_uses_two_fixture_versions() -> None:
    dataset = build_change_aware_ingestion_dataset()
    changed_case = dataset.cases[2]

    assert len(changed_case.inputs.fixture_paths) == 2
    assert changed_case.inputs.fixture_path is None
