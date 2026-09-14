"""Validation tests for project JSON dataset definitions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from evals.harness.dataset_loader import (
    build_json_dataset,
    load_dataset_definition,
)


def _definition() -> dict:
    return {
        "version": 2,
        "task": "retrieval",
        "name": "example/dataset",
        "knowledge": {
            "source": "fixtures",
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
                    {
                        "type": "tool_evidence_contains_terms",
                        "required_terms": ["software engineer"],
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

    definition = load_dataset_definition(path)
    loaded = build_json_dataset(path, timeout_seconds=1)

    assert definition.name == "example/dataset"
    assert definition.cases[0].name == "example"
    assert definition.vocabularies["missing"] == ("unknown", "unavailable")
    assert loaded.execution_target == "local_evaluation_team"
    assert loaded.dataset.cases[0].inputs.knowledge_fixture.records[0].name == "Jane Doe"
    assert len(loaded.dataset.cases[0].evaluators) == 3


def test_loader_selects_running_system_for_real_knowledge(tmp_path: Path) -> None:
    value = _definition()
    value["knowledge"] = {"source": "running_system"}

    loaded = build_json_dataset(_write_json(tmp_path, value), timeout_seconds=1)

    assert loaded.execution_target == "running_system"
    assert loaded.dataset.cases[0].inputs.knowledge_fixture is None


def test_loader_rejects_unknown_fields(tmp_path: Path) -> None:
    value = _definition()
    value["arbitrary_python"] = 'eval("unsafe")'

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        load_dataset_definition(_write_json(tmp_path, value))


def test_loader_rejects_unknown_evaluator_type(tmp_path: Path) -> None:
    value = _definition()
    value["cases"][0]["evaluators"] = [{"type": "execute_python"}]

    with pytest.raises(ValidationError, match="union_tag_invalid"):
        load_dataset_definition(_write_json(tmp_path, value))


def test_loader_rejects_missing_vocabulary_reference(tmp_path: Path) -> None:
    value = _definition()
    value["cases"][0]["evaluators"][0]["accepted_terms_ref"] = "absent"

    with pytest.raises(ValidationError, match="unknown vocabulary"):
        load_dataset_definition(_write_json(tmp_path, value))


def test_loader_rejects_missing_fixture_reference(tmp_path: Path) -> None:
    value = _definition()
    value["cases"][0]["fixture"] = "absent"

    with pytest.raises(ValidationError, match="unknown fixture"):
        load_dataset_definition(_write_json(tmp_path, value))


def test_published_schema_accepts_all_datasets() -> None:
    schema_path = Path("evals/datasets/schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    for dataset_path in Path("evals/datasets").glob("*.json"):
        if dataset_path == schema_path:
            continue
        dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
        validator.validate(dataset)
        load_dataset_definition(dataset_path)
