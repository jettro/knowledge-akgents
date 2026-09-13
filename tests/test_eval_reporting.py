"""Tests for native evaluation report persistence."""

from __future__ import annotations

from pathlib import Path

from pydantic_evals import Case, Dataset

from evals.reporting import load_report, save_report


def test_report_round_trip_supports_baseline_rendering(tmp_path: Path) -> None:
    dataset = Dataset(name="report-round-trip", cases=[Case(name="one", inputs=1)])
    report = dataset.evaluate_sync(lambda value: value + 1, progress=False)
    report_path = tmp_path / "reports" / "baseline.json"

    save_report(report, str(report_path))
    baseline = load_report(str(report_path))

    assert baseline.name == report.name
    assert baseline.cases[0].name == "one"
    assert baseline.cases[0].output == 2
    assert report.render(baseline=baseline)
