"""Runtime boundary and generic conversation execution."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Protocol, TypeVar

from pydantic import BaseModel, Field, model_validator

from akgentic_evals.collector import EvaluationEventCollector
from akgentic_evals.completion import CompletionPolicy
from akgentic_evals.events import AkgenticEvalEvent
from akgentic_evals.models import AkgenticCaseOutput

EventHandler = Callable[[AkgenticEvalEvent], None]
CaseInputT_contra = TypeVar(
    "CaseInputT_contra",
    bound="AkgenticCaseInput",
    contravariant=True,
)


class ConversationTurn(BaseModel):
    message: str
    target: str | None = None


class AkgenticCaseInput(BaseModel):
    message: str | None = None
    target: str | None = None
    turns: list[ConversationTurn] = Field(default_factory=list)
    timeout_seconds: float = Field(default=180.0, gt=0)

    @model_validator(mode="after")
    def validate_turns(self) -> AkgenticCaseInput:
        if bool(self.message) == bool(self.turns):
            raise ValueError("Provide either message or turns")
        return self

    def ordered_turns(self) -> list[ConversationTurn]:
        if self.turns:
            return self.turns
        assert self.message is not None
        return [ConversationTurn(message=self.message, target=self.target)]

class RuntimeCapabilities(BaseModel):
    model_config = {"frozen": True}

    request_correlation: bool
    isolated_execution: bool
    quiescence_detection: bool
    trace_context: bool


class AkgenticEvalRuntime(Protocol):
    """Drive one isolated application runtime and emit normalized events."""

    @property
    def capabilities(self) -> RuntimeCapabilities: ...

    def start(self, event_handler: EventHandler) -> None: ...

    def send(self, turn: ConversationTurn) -> None: ...

    def shutdown(self) -> None: ...


class AkgenticRuntimeFactory(Protocol[CaseInputT_contra]):
    """Create one case-scoped runtime from an application-owned input type."""

    def runtime(
        self,
        inputs: CaseInputT_contra,
    ) -> AbstractContextManager[AkgenticEvalRuntime]: ...


def run_case(
    inputs: AkgenticCaseInput,
    runtime: AkgenticEvalRuntime,
    *,
    completion_policy: CompletionPolicy | None = None,
) -> AkgenticCaseOutput:
    """Execute ordered turns and always release the runtime."""

    collector = EvaluationEventCollector(completion_policy=completion_policy)
    try:
        runtime.start(collector.on_event)
        output: AkgenticCaseOutput | None = None
        for response_count, turn in enumerate(inputs.ordered_turns(), start=1):
            runtime.send(turn)
            output = collector.wait_for_responses(
                response_count,
                inputs.timeout_seconds,
            )
            if output.completion_reason != collector.completion_reason:
                break
        assert output is not None
        return output
    finally:
        runtime.shutdown()


def run_case_with_factory[CaseInputT: AkgenticCaseInput](
    inputs: CaseInputT,
    runtime_factory: AkgenticRuntimeFactory[CaseInputT],
    *,
    completion_policy: CompletionPolicy | None = None,
) -> AkgenticCaseOutput:
    """Create a case-scoped runtime without interpreting application configuration."""

    with runtime_factory.runtime(inputs) as runtime:
        return run_case(
            inputs,
            runtime,
            completion_policy=completion_policy,
        )
