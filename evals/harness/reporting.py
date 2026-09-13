"""Persistence helpers for native Pydantic Evals reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic_evals.reporting import EvaluationReport, EvaluationReportAdapter


def save_report(report: EvaluationReport[Any, Any, Any], path: str) -> None:
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_bytes(EvaluationReportAdapter.dump_json(report, indent=2))


def load_report(path: str) -> EvaluationReport[Any, Any, Any]:
    return EvaluationReportAdapter.validate_json(Path(path).read_bytes())
