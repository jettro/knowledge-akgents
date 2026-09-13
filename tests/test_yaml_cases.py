"""Validation tests for contributor-authored evaluation YAML."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from evals.yaml_cases import load_dataset_definition, resolve_case_path


def _write_yaml(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "cases.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_loader_accepts_allow_listed_case_and_evaluator_fields(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """
version: 1
name: example/dataset
default_fixture: fixture.json
vocabularies:
  missing: [unknown, unavailable]
cases:
  - name: example
    message: What is known?
    metadata:
      prompt_variant: canonical
    evaluators:
      - type: human_response_contains_any_term
        accepted_terms_ref: missing
      - type: tool_call_count
        tool_name: search_graph
        minimum: 1
        maximum: 2
""",
    )

    definition = load_dataset_definition(path)

    assert definition.name == "example/dataset"
    assert definition.cases[0].name == "example"
    assert definition.vocabularies["missing"] == ("unknown", "unavailable")


def test_loader_rejects_unknown_fields(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """
version: 1
name: example/dataset
cases:
  - name: example
    message: What is known?
    arbitrary_python: eval("unsafe")
""",
    )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        load_dataset_definition(path)


def test_loader_rejects_unknown_evaluator_type(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """
version: 1
name: example/dataset
cases:
  - name: example
    message: What is known?
    evaluators:
      - type: execute_python
""",
    )

    with pytest.raises(ValidationError, match="union_tag_invalid"):
        load_dataset_definition(path)


def test_loader_rejects_missing_vocabulary_reference(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """
version: 1
name: example/dataset
cases:
  - name: example
    message: What is known?
    evaluators:
      - type: human_response_contains_any_term
        accepted_terms_ref: absent
""",
    )

    with pytest.raises(ValidationError, match="unknown vocabulary"):
        load_dataset_definition(path)


def test_fixture_paths_cannot_escape_allowed_root(tmp_path: Path) -> None:
    config_dir = tmp_path / "cases"
    config_dir.mkdir()
    config_path = config_dir / "dataset.yaml"
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}", encoding="utf-8")

    try:
        with pytest.raises(ValueError, match="escapes"):
            resolve_case_path(config_path, "../../outside.json", tmp_path)
    finally:
        outside.unlink()
