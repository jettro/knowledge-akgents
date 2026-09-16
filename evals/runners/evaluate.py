"""Run Knowledge Akgents evaluation datasets and save native reports."""

from __future__ import annotations

import argparse
import json
from functools import partial
from pathlib import Path

import logfire

from akgentic_evals.datasets import UnknownCaseError, select_case
from akgentic_evals.diagnostics import OutputInventory, SpanInventory
from akgentic_evals.reporting import load_report, save_report
from akgentic_evals.runtime import run_case_with_factory
from evals.evaluators.retrieval import RetrievalAnswerJudges
from evals.harness.catalog import TeamCatalog
from evals.harness.dataset_loader import (
    RETRIEVAL_DATASET_PATH,
    build_json_dataset,
)
from evals.harness.running_system import (
    RUNNING_SYSTEM_CAPABILITIES,
    require_running_system,
    run_running_system_case,
)
from evals.harness.runtime import KnowledgeRuntimeFactory, KnowledgeTeamRuntime
from evals.runners._cli import positive_int
from evals.scenarios.change_aware_ingestion import build_change_aware_ingestion_dataset
from evals.scenarios.jettro_ingestion import build_jettro_ingestion_dataset
from evals.scenarios.jettro_scenario import build_jettro_scenario_dataset
from evals.scenarios.no_useful_content import (
    build_no_useful_content_scenario_dataset,
)
from evals.scenarios.production_e2e import build_production_e2e_dataset
from evals.scenarios.prompt_injection import (
    build_prompt_injection_scenario_dataset,
)
from evals.scenarios.routing import build_routing_dataset
from evals.scenarios.unreachable_url import (
    build_unreachable_url_scenario_dataset,
)
from evals.scenarios.yuma_scenario import build_yuma_scenario_dataset
from knowledge_akgents.settings import settings


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--send-to-logfire",
        action="store_true",
        help="Export the experiment to the configured Logfire project.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="Maximum seconds to wait for a final human-directed response.",
    )
    parser.add_argument(
        "--allow-persistent-store",
        action="store_true",
        help="Allow a Python scenario to use the configured persistent Qdrant store.",
    )
    parser.add_argument(
        "--system-url",
        default="http://localhost:8000",
        help="Base URL of the running application used by running_system datasets.",
    )
    parser.add_argument(
        "--verbose-output",
        action="store_true",
        help="Include the complete structured case output in the report.",
    )
    parser.add_argument(
        "--scenario",
        choices=(
            "ingestion",
            "jettro-multi-turn",
            "yuma-multi-turn",
            "production-e2e",
            "retrieval-only",
            "prompt-injection",
            "no-useful-content",
            "unreachable-url",
            "routing",
            "change-aware-ingestion",
        ),
        default="ingestion",
        help="Select the evaluation case to run.",
    )
    parser.add_argument(
        "--catalog-team",
        choices=("evaluation", "production"),
        default=None,
        help=(
            "Select a team for Python scenarios. JSON datasets derive the team "
            "from knowledge.source and reject conflicting overrides."
        ),
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        help=(
            "Load a self-contained retrieval Dataset from one validated project "
            "JSON file instead of a registered scenario."
        ),
    )
    parser.add_argument(
        "--repeat",
        type=positive_int,
        default=1,
        help="Number of times Pydantic Evals should execute each case.",
    )
    parser.add_argument(
        "--case",
        help="Run only the named case from the selected dataset.",
    )
    parser.add_argument(
        "--with-judges",
        action="store_true",
        help="Run the calibrated groundedness and relevance judges.",
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
    loaded_json = (
        build_json_dataset(args.dataset, args.timeout)
        if args.dataset is not None
        else None
    )
    if loaded_json is not None and args.catalog_team is not None:
        raise SystemExit(
            "JSON datasets select their execution target through knowledge.source; "
            "remove --catalog-team."
        )
    catalog_team: TeamCatalog = args.catalog_team or "evaluation"
    uses_running_system = (
        loaded_json is not None
        and loaded_json.execution_target == "running_system"
    )
    if _requires_local_model(
        uses_running_system=uses_running_system,
        with_judges=args.with_judges,
    ) and not settings.openai_api_key:
        raise SystemExit("Missing required evaluation setting: OPENAI_API_KEY")
    if uses_running_system:
        try:
            require_running_system(args.system_url)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
    if not uses_running_system and settings.qdrant_enabled and not args.allow_persistent_store:
        raise SystemExit(
            "Persistent Qdrant is configured. Run with AKGENTIC_QDRANT_URL='' "
            "for an isolated scenario, or explicitly pass --allow-persistent-store."
        )
    if args.dataset is None and catalog_team == "production" and args.scenario not in {
        "ingestion",
        "jettro-multi-turn",
        "yuma-multi-turn",
        "production-e2e",
    }:
        raise SystemExit(
            "The production catalog team is supported only for ingestion, "
            "jettro-multi-turn, and yuma-multi-turn. Other scenarios depend on "
            "synthetic fixture failures or preloaded fixture knowledge."
        )
    if args.scenario == "production-e2e" and catalog_team != "production":
        raise SystemExit("The production-e2e scenario requires --catalog-team production.")

    logfire.configure(
        send_to_logfire=args.send_to_logfire,
        service_name="knowledge-akgents-evals",
        environment="development",
        console=False,
    )
    logfire.instrument_pydantic_ai()

    if loaded_json is not None:
        dataset = loaded_json.dataset
    elif args.scenario == "jettro-multi-turn":
        dataset = build_jettro_scenario_dataset(args.timeout)
    elif args.scenario == "yuma-multi-turn":
        dataset = build_yuma_scenario_dataset(args.timeout)
    elif args.scenario == "production-e2e":
        dataset = build_production_e2e_dataset(args.timeout)
    elif args.scenario == "prompt-injection":
        dataset = build_prompt_injection_scenario_dataset(args.timeout)
    elif args.scenario == "no-useful-content":
        dataset = build_no_useful_content_scenario_dataset(args.timeout)
    elif args.scenario == "unreachable-url":
        dataset = build_unreachable_url_scenario_dataset(args.timeout)
    elif args.scenario == "routing":
        dataset = build_routing_dataset(args.timeout)
    elif args.scenario == "change-aware-ingestion":
        dataset = build_change_aware_ingestion_dataset(args.timeout)
    elif args.scenario == "retrieval-only":
        dataset = build_json_dataset(
            RETRIEVAL_DATASET_PATH,
            args.timeout,
        ).dataset
    else:
        dataset = build_jettro_ingestion_dataset(args.timeout)
    try:
        select_case(dataset, args.case)
    except UnknownCaseError as exc:
        raise SystemExit(str(exc)) from exc
    if args.with_judges:
        if args.scenario != "retrieval-only" and args.dataset is None:
            raise SystemExit(
                "--with-judges currently supports only retrieval fixture datasets"
            )
        dataset.add_evaluator(
            RetrievalAnswerJudges(
                model=f"{settings.llm_provider}:{settings.llm_model}",
            )
        )
    dataset.add_evaluator(OutputInventory())
    dataset.add_evaluator(SpanInventory())
    run_name = dataset.name
    task = (
        partial(run_running_system_case, system_url=args.system_url)
        if uses_running_system
        else partial(
            run_case_with_factory,
            runtime_factory=KnowledgeRuntimeFactory(catalog_team),
        )
    )
    execution_target = (
        loaded_json.execution_target
        if loaded_json is not None
        else f"local_{catalog_team}_team"
    )
    report = dataset.evaluate_sync(
        task,
        name=run_name,
        max_concurrency=1,
        repeat=args.repeat,
        metadata={
            "agent_model": None if uses_running_system else settings.llm_model,
            "judge_model": (
                f"{settings.llm_provider}:{settings.llm_model}"
                if args.with_judges
                else None
            ),
            "logfire_export": args.send_to_logfire,
            "purpose": "application acceptance and regression evaluation",
            "repeat": args.repeat,
            "retrieval_answer_judges": args.with_judges,
            "execution_target": execution_target,
            "runtime_capabilities": (
                RUNNING_SYSTEM_CAPABILITIES.model_dump()
                if uses_running_system
                else KnowledgeTeamRuntime.capabilities.model_dump()
            ),
            "system_url": args.system_url if uses_running_system else None,
            "dataset_path": str(args.dataset) if args.dataset is not None else None,
        },
    )
    baseline = load_report(args.baseline) if args.baseline else None
    report.print(
        baseline=baseline,
        include_input=True,
        include_metadata=True,
        include_output=args.verbose_output,
        include_reasons=True,
    )
    if args.save_report:
        save_report(report, args.save_report)
    summaries = []
    for case in report.cases:
        output = case.output
        successful_invocation_ids = {
            invocation.id for invocation in output.tool_invocations(successful=True)
        }
        summaries.append(
            {
                "case": case.name,
                "completion_reason": output.completion_reason,
                "human_responses": output.human_responses,
                "route": [[message.sender, message.recipient] for message in output.messages],
                "tools": [
                    {
                        "name": call.tool_name,
                        "arguments": call.arguments,
                        "succeeded": call.invocation_id in successful_invocation_ids,
                    }
                    for call in output.tool_calls
                ],
                "tool_evidence_count": len(output.tool_evidence),
                "usage": {
                    "models": sorted({usage.model_name for usage in output.llm_usage}),
                    "providers": sorted({usage.provider_name for usage in output.llm_usage}),
                    "responses": len(output.llm_usage),
                    "requests": sum(usage.requests for usage in output.llm_usage),
                    "input_tokens": sum(usage.input_tokens for usage in output.llm_usage),
                    "output_tokens": sum(usage.output_tokens for usage in output.llm_usage),
                    "cache_read_tokens": sum(usage.cache_read_tokens for usage in output.llm_usage),
                    "cache_write_tokens": sum(
                        usage.cache_write_tokens for usage in output.llm_usage
                    ),
                },
                "final_response": output.final_response,
                "errors": output.errors,
            }
        )
    if summaries:
        print(json.dumps(summaries, indent=2))


def _requires_local_model(
    *,
    uses_running_system: bool,
    with_judges: bool,
) -> bool:
    return not uses_running_system or with_judges


if __name__ == "__main__":
    main()
