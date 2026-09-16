"""Deterministic evaluators for normalized Akgentic evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic_evals.evaluators import (
    EvaluationReason,
    Evaluator,
    EvaluatorContext,
    EvaluatorOutput,
)

from akgentic_evals.models import AkgenticCaseOutput

Metadata = dict[str, Any]
EvaluationContext = EvaluatorContext[Any, AkgenticCaseOutput, Metadata]


@dataclass
class CompletedSuccessfully(Evaluator[Any, AkgenticCaseOutput, Metadata]):
    expected_human_responses: int = 1
    completion_reason: str = "human_response"

    def evaluate(self, ctx: EvaluationContext) -> EvaluatorOutput:
        completed = (
            ctx.output.completion_reason == self.completion_reason
            and len(ctx.output.human_responses) >= self.expected_human_responses
        )
        return {
            "received_final_response": EvaluationReason(
                value=completed and ctx.output.final_response is not None,
                reason=(
                    f"completion_reason={ctx.output.completion_reason}, "
                    f"human_responses={len(ctx.output.human_responses)}"
                ),
            ),
            "no_actor_errors": EvaluationReason(
                value=not ctx.output.errors,
                reason=(
                    "; ".join(ctx.output.errors)
                    if ctx.output.errors
                    else "No actor errors"
                ),
            ),
        }


@dataclass
class FollowedMessageRoute(Evaluator[Any, AkgenticCaseOutput, Metadata]):
    expected_route: tuple[tuple[str, str], ...]

    def evaluate(self, ctx: EvaluationContext) -> EvaluationReason:
        actual = [
            (message.sender or "", message.recipient or "")
            for message in ctx.output.messages
        ]
        matched = is_ordered_subsequence(list(self.expected_route), actual)
        return EvaluationReason(value=matched, reason=f"Observed route: {actual}")


@dataclass
class DidNotInvolveActors(Evaluator[Any, AkgenticCaseOutput, Metadata]):
    actor_names: tuple[str, ...]

    def evaluate(self, ctx: EvaluationContext) -> EvaluationReason:
        observed = {
            actor
            for message in ctx.output.messages
            for actor in (message.sender, message.recipient)
            if actor
        }
        unexpected = sorted(set(self.actor_names) & observed)
        return EvaluationReason(
            value=not unexpected,
            reason=(
                f"Unexpected actors involved: {unexpected}"
                if unexpected
                else f"Excluded actors were not involved: {list(self.actor_names)}"
            ),
        )


@dataclass
class CalledRequiredTools(Evaluator[Any, AkgenticCaseOutput, Metadata]):
    required_tools: tuple[str, ...]

    def evaluate(self, ctx: EvaluationContext) -> EvaluatorOutput:
        observed = {call.tool_name for call in ctx.output.tool_calls}
        return {
            tool_name: EvaluationReason(
                value=tool_name in observed,
                reason=f"Observed tools: {sorted(observed)}",
            )
            for tool_name in self.required_tools
        }


@dataclass
class ToolCallsInOrder(Evaluator[Any, AkgenticCaseOutput, Metadata]):
    expected_tools: tuple[str, ...]

    def evaluate(self, ctx: EvaluationContext) -> EvaluationReason:
        observed = [call.tool_name for call in ctx.output.tool_calls]
        matched = is_ordered_subsequence(list(self.expected_tools), observed)
        return EvaluationReason(value=matched, reason=f"Observed tool order: {observed}")


@dataclass
class DidNotCallTools(Evaluator[Any, AkgenticCaseOutput, Metadata]):
    forbidden_tools: tuple[str, ...]

    def evaluate(self, ctx: EvaluationContext) -> EvaluatorOutput:
        observed = {call.tool_name for call in ctx.output.tool_calls}
        return {
            f"did_not_call_{tool_name}": EvaluationReason(
                value=tool_name not in observed,
                reason=f"Observed tools: {sorted(observed)}",
            )
            for tool_name in self.forbidden_tools
        }


@dataclass
class ToolArgumentsContain(Evaluator[Any, AkgenticCaseOutput, Metadata]):
    tool_name: str
    argument_name: str
    expected_value: Any

    def evaluate(self, ctx: EvaluationContext) -> EvaluationReason:
        matching_calls = [
            call for call in ctx.output.tool_calls if call.tool_name == self.tool_name
        ]
        observed_values = [
            call.arguments.get(self.argument_name)
            for call in matching_calls
            if isinstance(call.arguments, dict)
        ]
        matched = any(
            contains_expected(value, self.expected_value) for value in observed_values
        )
        return EvaluationReason(
            value=matched,
            reason=f"Observed {self.argument_name} values: {observed_values}",
        )


@dataclass
class ToolArgumentsDoNotContainTerms(
    Evaluator[Any, AkgenticCaseOutput, Metadata]
):
    tool_name: str
    forbidden_terms: tuple[str, ...]

    def evaluate(self, ctx: EvaluationContext) -> EvaluationReason:
        matching_calls = [
            call for call in ctx.output.tool_calls if call.tool_name == self.tool_name
        ]
        serialized = [
            json.dumps(call.arguments, ensure_ascii=False, sort_keys=True).casefold()
            for call in matching_calls
        ]
        matched = sorted(
            {
                term
                for term in self.forbidden_terms
                if any(term.casefold() in arguments for arguments in serialized)
            }
        )
        return EvaluationReason(
            value=bool(matching_calls) and not matched,
            reason=(
                f"Forbidden terms in {self.tool_name} arguments: {matched}"
                if matched
                else f"Observed {len(matching_calls)} clean {self.tool_name} call(s)"
            ),
        )


@dataclass
class ToolCallsSucceeded(Evaluator[Any, AkgenticCaseOutput, Metadata]):
    tool_names: tuple[str, ...] | None = None

    def evaluate(self, ctx: EvaluationContext) -> EvaluatorOutput:
        selected_calls = [
            call
            for call in ctx.output.tool_calls
            if self.tool_names is None or call.tool_name in self.tool_names
        ]
        invocation_ids = {call.invocation_id for call in selected_calls}
        successful_return_ids = {
            result.invocation_id for result in ctx.output.tool_returns if result.success
        }
        return {
            "tool_arguments_parseable": bool(selected_calls)
            and all(call.parse_error is None for call in selected_calls),
            "tool_calls_succeeded": bool(invocation_ids)
            and invocation_ids <= successful_return_ids,
        }


@dataclass
class ToolEvidenceContainsTerms(Evaluator[Any, AkgenticCaseOutput, Metadata]):
    tool_name: str
    required_terms: tuple[str, ...]

    def evaluate(self, ctx: EvaluationContext) -> EvaluationReason:
        evidence = "\n".join(
            record.content
            for record in ctx.output.successful_tool_evidence(self.tool_name)
        ).casefold()
        missing = [
            term for term in self.required_terms if term.casefold() not in evidence
        ]
        return EvaluationReason(
            value=bool(evidence) and not missing,
            reason=(
                f"Missing {self.tool_name} evidence terms: {missing}"
                if missing
                else "All required tool-evidence terms present"
            ),
        )


@dataclass
class AnswerContainsTerms(Evaluator[Any, AkgenticCaseOutput, Metadata]):
    required_terms: tuple[str, ...]

    def evaluate(self, ctx: EvaluationContext) -> EvaluationReason:
        answer = (ctx.output.final_response or "").casefold()
        missing = [term for term in self.required_terms if term.casefold() not in answer]
        return EvaluationReason(
            value=not missing,
            reason=(
                f"Missing required terms: {missing}"
                if missing
                else "All required terms present"
            ),
        )


@dataclass
class HumanResponseContainsTerms(Evaluator[Any, AkgenticCaseOutput, Metadata]):
    response_index: int
    required_terms: tuple[str, ...]

    def evaluate(self, ctx: EvaluationContext) -> EvaluationReason:
        response = _response_at(ctx.output, self.response_index)
        if response is None:
            return _missing_response_reason(ctx.output, self.response_index)

        missing = [
            term for term in self.required_terms if term.casefold() not in response.casefold()
        ]
        return EvaluationReason(
            value=not missing,
            reason=(
                f"Missing required terms: {missing}"
                if missing
                else "All required terms present"
            ),
        )


@dataclass
class HumanResponseContainsAnyTerm(Evaluator[Any, AkgenticCaseOutput, Metadata]):
    response_index: int
    accepted_terms: tuple[str, ...]

    def evaluate(self, ctx: EvaluationContext) -> EvaluationReason:
        response = _response_at(ctx.output, self.response_index)
        if response is None:
            return _missing_response_reason(ctx.output, self.response_index)

        matched = [
            term for term in self.accepted_terms if term.casefold() in response.casefold()
        ]
        return EvaluationReason(
            value=bool(matched),
            reason=f"Matched accepted terms: {matched}",
        )


@dataclass
class HumanResponsesDoNotContainTerms(
    Evaluator[Any, AkgenticCaseOutput, Metadata]
):
    forbidden_terms: tuple[str, ...]

    def evaluate(self, ctx: EvaluationContext) -> EvaluationReason:
        responses = [response.casefold() for response in ctx.output.human_responses]
        matched = sorted(
            {
                term
                for term in self.forbidden_terms
                if any(term.casefold() in response for response in responses)
            }
        )
        return EvaluationReason(
            value=not matched,
            reason=(
                f"Forbidden response terms: {matched}"
                if matched
                else "No forbidden terms"
            ),
        )


@dataclass
class ToolCallCount(Evaluator[Any, AkgenticCaseOutput, Metadata]):
    tool_name: str
    minimum: int
    maximum: int | None = None

    def evaluate(self, ctx: EvaluationContext) -> EvaluationReason:
        count = sum(call.tool_name == self.tool_name for call in ctx.output.tool_calls)
        within_maximum = self.maximum is None or count <= self.maximum
        return EvaluationReason(
            value=count >= self.minimum and within_maximum,
            reason=(
                f"Observed {count} calls; expected at least {self.minimum}"
                + (f" and at most {self.maximum}" if self.maximum is not None else "")
            ),
        )


@dataclass
class LlmUsageWithinLimits(Evaluator[Any, AkgenticCaseOutput, Metadata]):
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    max_requests: int | None = None
    require_usage: bool = True

    def evaluate(self, ctx: EvaluationContext) -> EvaluationReason:
        input_tokens = sum(record.input_tokens for record in ctx.output.llm_usage)
        output_tokens = sum(record.output_tokens for record in ctx.output.llm_usage)
        requests = sum(record.requests for record in ctx.output.llm_usage)
        within_limits = (
            (self.max_input_tokens is None or input_tokens <= self.max_input_tokens)
            and (
                self.max_output_tokens is None
                or output_tokens <= self.max_output_tokens
            )
            and (self.max_requests is None or requests <= self.max_requests)
        )
        usage_present = bool(ctx.output.llm_usage) or not self.require_usage
        return EvaluationReason(
            value=usage_present and within_limits,
            reason=(
                f"Observed input_tokens={input_tokens}, "
                f"output_tokens={output_tokens}, requests={requests}"
            ),
        )


def is_ordered_subsequence(expected: list[Any], actual: list[Any]) -> bool:
    remaining = iter(actual)
    return all(any(candidate == item for candidate in remaining) for item in expected)


def contains_expected(observed: Any, expected: Any) -> bool:
    if isinstance(observed, list):
        return any(contains_expected(item, expected) for item in observed)
    if isinstance(observed, str) and isinstance(expected, str):
        return observed.rstrip("/") == expected.rstrip("/")
    return observed == expected


def _response_at(output: AkgenticCaseOutput, response_index: int) -> str | None:
    if response_index >= len(output.human_responses):
        return None
    return output.human_responses[response_index]


def _missing_response_reason(
    output: AkgenticCaseOutput,
    response_index: int,
) -> EvaluationReason:
    return EvaluationReason(
        value=False,
        reason=(
            f"Expected response index {response_index}, "
            f"observed {len(output.human_responses)} responses"
        ),
    )
