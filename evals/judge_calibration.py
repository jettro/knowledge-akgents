"""Run the static human-labeled LLM-judge calibration dataset."""

from __future__ import annotations

import argparse
import json

import logfire

from evals.cli import positive_int
from evals.datasets.judge_calibration import (
    build_judge_calibration_dataset,
    return_candidate_answer,
)
from evals.reporting import load_report, save_report
from knowledge_akgents.settings import settings


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--send-to-logfire",
        action="store_true",
        help="Export the calibration experiment to the configured Logfire project.",
    )
    parser.add_argument(
        "--repeat",
        type=positive_int,
        default=1,
        help="Number of times Pydantic Evals should execute each calibration case.",
    )
    parser.add_argument(
        "--save-report",
        help="Write the native Pydantic Evals report JSON to this path.",
    )
    parser.add_argument(
        "--baseline",
        help="Compare the new report with a previously saved report JSON.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if not settings.openai_api_key:
        raise SystemExit("Missing required live-evaluation setting: OPENAI_API_KEY")

    logfire.configure(
        send_to_logfire=args.send_to_logfire,
        service_name="knowledge-akgents-evals",
        environment="development",
        console=False,
    )

    judge_model = f"{settings.llm_provider}:{settings.llm_model}"
    dataset = build_judge_calibration_dataset(judge_model)
    report = dataset.evaluate_sync(
        return_candidate_answer,
        name="judge-calibration",
        max_concurrency=1,
        repeat=args.repeat,
        metadata={
            "judge_model": judge_model,
            "logfire_export": args.send_to_logfire,
            "repeat": args.repeat,
        },
    )
    baseline = load_report(args.baseline) if args.baseline else None
    report.print(
        baseline=baseline,
        include_input=True,
        include_metadata=True,
        include_output=True,
        include_reasons=True,
    )
    if args.save_report:
        save_report(report, args.save_report)

    label_keys = {
        "groundedness": "human_grounded",
        "answer_relevance": "human_relevant",
    }
    comparisons = []
    by_dimension = {dimension: {"agreements": 0, "runs": 0} for dimension in label_keys}
    grouped: dict[str, dict[str, dict[str, int]]] = {}
    for case in report.cases:
        source_name = case.source_case_name or case.name
        group = grouped.setdefault(
            source_name,
            {dimension: {"agreements": 0, "runs": 0} for dimension in label_keys},
        )
        dimensions = {}
        for dimension, label_key in label_keys.items():
            judge_result = case.assertions.get(dimension)
            if judge_result is None:
                raise RuntimeError(
                    f"Missing {dimension} assertion for {case.name}; "
                    f"observed {sorted(case.assertions)}"
                )
            human_pass = bool(case.metadata and case.metadata[label_key])
            agrees = human_pass == judge_result.value
            dimensions[dimension] = {
                "human_pass": human_pass,
                "judge_pass": judge_result.value,
                "agrees": agrees,
                "reason": judge_result.reason,
            }
            by_dimension[dimension]["runs"] += 1
            by_dimension[dimension]["agreements"] += agrees
            group[dimension]["runs"] += 1
            group[dimension]["agreements"] += agrees
        comparisons.append({"case": case.name, "dimensions": dimensions})

    print(
        json.dumps(
            {
                "agreement": sum(
                    dimension["agrees"]
                    for item in comparisons
                    for dimension in item["dimensions"].values()
                ),
                "decision_count": len(comparisons) * len(label_keys),
                "by_dimension": by_dimension,
                "by_source_case": grouped,
                "cases": comparisons,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
