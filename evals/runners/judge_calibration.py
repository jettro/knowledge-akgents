"""Run the static human-labeled LLM-judge calibration dataset."""

from __future__ import annotations

import argparse
import json

import logfire

from akgentic_evals.calibration import summarize_judge_agreement
from akgentic_evals.reporting import load_report, save_report
from evals.harness.cli import positive_int
from evals.scenarios.judge_calibration import (
    build_judge_calibration_dataset,
    return_candidate_answer,
)
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

    summary = summarize_judge_agreement(
        report,
        {
            "groundedness": "human_grounded",
            "answer_relevance": "human_relevant",
        },
    )
    print(json.dumps(summary.model_dump(), indent=2))


if __name__ == "__main__":
    main()
