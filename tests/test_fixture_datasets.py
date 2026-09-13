"""Validation tests for self-contained JSON fixture datasets."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from evals.fixture_datasets import (
    build_fixture_dataset,
    load_fixture_dataset_definition,
)


def _definition() -> dict:
    return {
        "version": 1,
        "task": "retrieval",
        "name": "example/dataset",
        "default_fixture": "example",
        "fixtures": {
            "example": {
                "records": [
                    {
                        "name": "Jane Doe",
                        "entity_type": "Person",
                        "description": "Jane Doe is a software engineer.",
                    }
                ]
            }
        },
        "vocabularies": {"missing": ["unknown", "unavailable"]},
        "cases": [
            {
                "name": "example",
                "message": "What is known?",
                "metadata": {"prompt_variant": "canonical"},
                "evaluators": [
                    {
                        "type": "human_response_contains_any_term",
                        "accepted_terms_ref": "missing",
                    },
                    {
                        "type": "tool_call_count",
                        "tool_name": "search_graph",
                        "minimum": 1,
                        "maximum": 2,
                    },
                ],
            }
        ],
    }


def _write_json(tmp_path: Path, value: object) -> Path:
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_loader_accepts_allow_listed_fixture_case_and_evaluator_fields(
    tmp_path: Path,
) -> None:
    path = _write_json(tmp_path, _definition())

    definition = load_fixture_dataset_definition(path)
    dataset = build_fixture_dataset(path, timeout_seconds=1)

    assert definition.name == "example/dataset"
    assert definition.cases[0].name == "example"
    assert definition.vocabularies["missing"] == ("unknown", "unavailable")
    assert dataset.cases[0].inputs.knowledge_fixture.records[0].name == "Jane Doe"


def test_loader_rejects_unknown_fields(tmp_path: Path) -> None:
    value = _definition()
    value["arbitrary_python"] = 'eval("unsafe")'

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        load_fixture_dataset_definition(_write_json(tmp_path, value))


def test_loader_rejects_unknown_evaluator_type(tmp_path: Path) -> None:
    value = _definition()
    value["cases"][0]["evaluators"] = [{"type": "execute_python"}]

    with pytest.raises(ValidationError, match="union_tag_invalid"):
        load_fixture_dataset_definition(_write_json(tmp_path, value))


def test_loader_rejects_missing_vocabulary_reference(tmp_path: Path) -> None:
    value = _definition()
    value["cases"][0]["evaluators"][0]["accepted_terms_ref"] = "absent"

    with pytest.raises(ValidationError, match="unknown vocabulary"):
        load_fixture_dataset_definition(_write_json(tmp_path, value))


def test_loader_rejects_missing_fixture_reference(tmp_path: Path) -> None:
    value = _definition()
    value["cases"][0]["fixture"] = "absent"

    with pytest.raises(ValidationError, match="unknown fixture"):
        load_fixture_dataset_definition(_write_json(tmp_path, value))
