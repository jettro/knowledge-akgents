"""Diagnostic evaluators for normalized evaluation output and spans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic_evals.evaluators import Evaluator, EvaluatorContext, EvaluatorOutput

from akgentic_evals.models import AkgenticCaseOutput

DiagnosticContext = EvaluatorContext[Any, AkgenticCaseOutput, Any]


@dataclass
class OutputInventory(Evaluator[Any, AkgenticCaseOutput, Any]):
    """Summarize the normalized evidence captured for one case."""

    def evaluate(self, ctx: DiagnosticContext) -> EvaluatorOutput:
        call_ids = {call.invocation_id for call in ctx.output.tool_calls}
        return_ids = {result.invocation_id for result in ctx.output.tool_returns}
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
            "actor_error_count": len(ctx.output.errors),
            "llm_usage_event_count": len(ctx.output.llm_usage),
            "llm_request_count": sum(
                usage.requests for usage in ctx.output.llm_usage
            ),
            "input_token_count": sum(
                usage.input_tokens for usage in ctx.output.llm_usage
            ),
            "output_token_count": sum(
                usage.output_tokens for usage in ctx.output.llm_usage
            ),
            "cache_read_token_count": sum(
                usage.cache_read_tokens for usage in ctx.output.llm_usage
            ),
            "cache_write_token_count": sum(
                usage.cache_write_tokens for usage in ctx.output.llm_usage
            ),
        }


@dataclass
class SpanInventory(Evaluator[Any, AkgenticCaseOutput, Any]):
    """Summarize spans attached to one Pydantic Evals case."""

    max_names: int = 20

    def evaluate(self, ctx: DiagnosticContext) -> EvaluatorOutput:
        nodes = list(ctx.span_tree)
        names = sorted({node.name for node in nodes})
        return {
            "span_count": len(nodes),
            "tool_span_count": sum("tool" in node.name.lower() for node in nodes),
            "span_names": (
                " | ".join(names[: self.max_names]) if names else "<none>"
            ),
        }
