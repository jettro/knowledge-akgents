"""Tests for evaluation runner input handling."""

from __future__ import annotations

import argparse

import pytest

from akgentic_evals.datasets import UnknownCaseError, select_case
from evals.harness.dataset_loader import (
    RETRIEVAL_DATASET_PATH,
    build_json_dataset,
)
from evals.runners._cli import positive_int
from evals.runners.evaluate import _requires_local_model


def test_repeat_count_must_be_positive() -> None:
    assert positive_int("3") == 3

    with pytest.raises(argparse.ArgumentTypeError, match="value must be at least 1"):
        positive_int("0")


def test_running_system_without_local_judges_does_not_require_local_model() -> None:
    assert not _requires_local_model(
        uses_running_system=True,
        with_judges=False,
    )
    assert _requires_local_model(
        uses_running_system=True,
        with_judges=True,
    )
    assert _requires_local_model(
        uses_running_system=False,
        with_judges=False,
    )


def test_select_case_filters_dataset() -> None:
    dataset = build_json_dataset(RETRIEVAL_DATASET_PATH, timeout_seconds=1).dataset

    select_case(dataset, "jettro-unknown-favorite-database")

    assert [case.name for case in dataset.cases] == [
        "jettro-unknown-favorite-database"
    ]


def test_select_case_rejects_unknown_name() -> None:
    dataset = build_json_dataset(RETRIEVAL_DATASET_PATH, timeout_seconds=1).dataset

    with pytest.raises(UnknownCaseError, match="Unknown case"):
        select_case(dataset, "missing-case")
