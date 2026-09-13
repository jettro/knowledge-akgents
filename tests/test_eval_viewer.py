"""Compatibility checks for the local native-report viewer."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import EqualsExpected
from pydantic_evals.reporting import EvaluationReportAdapter

VIEWER_DIR = Path(__file__).parents[1] / "eval-viewer"


def test_native_report_contains_fields_used_by_viewer() -> None:
    dataset = Dataset(
        name="viewer-contract",
        cases=[Case(name="example", inputs={"question": "Example?"}, expected_output="yes")],
        evaluators=[EqualsExpected()],
    )
    report = dataset.evaluate_sync(lambda _: "yes", progress=False)

    payload = json.loads(EvaluationReportAdapter.dump_json(report))
    case = payload["cases"][0]
    assertion = case["assertions"]["EqualsExpected"]

    assert isinstance(payload["name"], str)
    assert isinstance(payload["cases"], list)
    assert {
        "name",
        "inputs",
        "metadata",
        "expected_output",
        "output",
        "metrics",
        "attributes",
        "scores",
        "labels",
        "assertions",
        "task_duration",
        "total_duration",
        "source_case_name",
        "evaluator_failures",
    } <= case.keys()
    assert {"name", "value", "reason"} <= assertion.keys()
    assert assertion["value"] is True


def test_viewer_page_references_existing_static_assets() -> None:
    html = (VIEWER_DIR / "index.html").read_text(encoding="utf-8")

    for asset in (
        "app.js",
        "styles.css",
        "favicon.svg",
        "favicon.ico",
        "apple-touch-icon.png",
    ):
        assert asset in html
        assert (VIEWER_DIR / asset).is_file()
