"""One-case spike for inspecting Akgentic events and Pydantic AI spans.

This intentionally exercises only the Jettro about-page ingestion path. It is a
diagnostic stepping stone, not the final evaluation harness.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from functools import partial

import logfire
from pydantic_evals import Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext, EvaluatorOutput

from evals.cli import positive_int
from evals.datasets.change_aware_ingestion import build_change_aware_ingestion_dataset
from evals.datasets.jettro_ingestion import build_jettro_ingestion_dataset
from evals.datasets.jettro_scenario import build_jettro_scenario_dataset
from evals.datasets.no_useful_content_scenario import (
    build_no_useful_content_scenario_dataset,
)
from evals.datasets.prompt_injection_scenario import (
    build_prompt_injection_scenario_dataset,
)
from evals.datasets.retrieval_only import build_retrieval_only_dataset
from evals.datasets.routing import build_routing_dataset
from evals.datasets.unreachable_url_scenario import (
    build_unreachable_url_scenario_dataset,
)
from evals.datasets.yuma_scenario import build_yuma_scenario_dataset
from evals.live_judges import LiveRetrievalJudges
from evals.models import TeamCaseInput, TeamCaseOutput
from evals.reporting import load_report, save_report
from evals.tasks import run_team_case
from knowledge_akgents.settings import settings


@dataclass
class EventInventory(Evaluator[TeamCaseInput, TeamCaseOutput, dict[str, str]]):
    def evaluate(
        self,
        ctx: EvaluatorContext[TeamCaseInput, TeamCaseOutput, dict[str, str]],
    ) -> EvaluatorOutput:
        call_ids = {call.tool_call_id for call in ctx.output.tool_calls}
        return_ids = {result.tool_call_id for result in ctx.output.tool_returns}
        empty_hire_calls = sum(
            call.tool_name == "hire_members"
            and isinstance(call.arguments, dict)
            and not call.arguments.get("roles")
            for call in ctx.output.tool_calls
        )
        return {
            "message_count": len(ctx.output.messages),
            "human_response_count": len(ctx.output.human_responses),
            "tool_call_count": len(ctx.output.tool_calls),
            "tool_return_count": len(ctx.output.tool_returns),
            "tool_evidence_count": len(ctx.output.tool_evidence),
            "tool_argument_parse_error_count": sum(
                call.parse_error is not None for call in ctx.output.tool_calls
            ),
            "uncorrelated_tool_call_count": len(call_ids - return_ids),
            "failed_tool_return_count": sum(
                not result.success for result in ctx.output.tool_returns
            ),
            "empty_hire_members_call_count": empty_hire_calls,
            "actor_error_count": len(ctx.output.errors),
            "llm_response_count": len(ctx.output.llm_usage),
            "llm_request_count": sum(usage.requests for usage in ctx.output.llm_usage),
            "input_token_count": sum(usage.input_tokens for usage in ctx.output.llm_usage),
            "output_token_count": sum(usage.output_tokens for usage in ctx.output.llm_usage),
            "cache_read_token_count": sum(
                usage.cache_read_tokens for usage in ctx.output.llm_usage
            ),
            "cache_write_token_count": sum(
                usage.cache_write_tokens for usage in ctx.output.llm_usage
            ),
        }


@dataclass
class SpanInventory(Evaluator[TeamCaseInput, TeamCaseOutput, dict[str, str]]):
    def evaluate(
        self,
        ctx: EvaluatorContext[TeamCaseInput, TeamCaseOutput, dict[str, str]],
    ) -> EvaluatorOutput:
        nodes = list(ctx.span_tree)
        names = sorted({node.name for node in nodes})
        return {
            "span_count": len(nodes),
            "tool_span_count": sum("tool" in node.name.lower() for node in nodes),
            "span_names": " | ".join(names[:20]) if names else "<none>",
        }


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
        help="Allow the spike to write to the configured persistent Qdrant store.",
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
        default="evaluation",
        help=(
            "Use the fixture-capable evaluation team or the exact production "
            "catalog team with isolated runtime state."
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


def _select_case(dataset: Dataset, case_name: str | None) -> None:
    if case_name is None:
        return
    selected = [case for case in dataset.cases if case.name == case_name]
    if not selected:
        available = ", ".join(case.name or "<unnamed>" for case in dataset.cases)
        raise SystemExit(f"Unknown case {case_name!r}. Available cases: {available}")
    dataset.cases[:] = selected


def main() -> None:
    args = _parse_args()
    missing = [name for name, value in (("OPENAI_API_KEY", settings.openai_api_key),) if not value]
    if missing:
        raise SystemExit(f"Missing required live-evaluation settings: {', '.join(missing)}")
    if settings.qdrant_enabled and not args.allow_persistent_store:
        raise SystemExit(
            "Persistent Qdrant is configured. Run with AKGENTIC_QDRANT_URL='' "
            "for an isolated in-memory spike, or explicitly pass --allow-persistent-store."
        )
    if args.catalog_team == "production" and args.scenario not in {
        "ingestion",
        "jettro-multi-turn",
        "yuma-multi-turn",
    }:
        raise SystemExit(
            "The production catalog team is supported only for ingestion, "
            "jettro-multi-turn, and yuma-multi-turn. Other scenarios depend on "
            "synthetic fixture failures or preloaded fixture knowledge."
        )

    logfire.configure(
        send_to_logfire=args.send_to_logfire,
        service_name="knowledge-akgents-evals",
        environment="development",
        console=False,
    )
    logfire.instrument_pydantic_ai()

    if args.scenario == "jettro-multi-turn":
        dataset = build_jettro_scenario_dataset(args.timeout)
    elif args.scenario == "yuma-multi-turn":
        dataset = build_yuma_scenario_dataset(args.timeout)
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
        dataset = build_retrieval_only_dataset(args.timeout)
    else:
        dataset = build_jettro_ingestion_dataset(args.timeout)
    _select_case(dataset, args.case)
    if args.with_judges:
        if args.scenario != "retrieval-only":
            raise SystemExit("--with-judges currently supports only retrieval-only cases")
        dataset.add_evaluator(
            LiveRetrievalJudges(
                model=f"{settings.llm_provider}:{settings.llm_model}",
            )
        )
    dataset.add_evaluator(EventInventory())
    dataset.add_evaluator(SpanInventory())
    report = dataset.evaluate_sync(
        partial(run_team_case, catalog_team=args.catalog_team),
        name=f"{args.scenario}-observability",
        max_concurrency=1,
        repeat=args.repeat,
        metadata={
            "model": settings.llm_model,
            "logfire_export": args.send_to_logfire,
            "purpose": "discover event and span contracts",
            "repeat": args.repeat,
            "live_judges": args.with_judges,
            "catalog_team": args.catalog_team,
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
                        "succeeded": any(
                            result.tool_call_id == call.tool_call_id and result.success
                            for result in output.tool_returns
                        ),
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


if __name__ == "__main__":
    main()
