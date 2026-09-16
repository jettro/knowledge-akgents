"""Normalized runtime events consumed by the reusable evaluation collector."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class MessageObserved(BaseModel):
    kind: Literal["message"] = "message"
    sender: str | None
    recipient: str | None
    message_type: str
    content: str


class ToolCalled(BaseModel):
    kind: Literal["tool_called"] = "tool_called"
    run_id: str
    tool_name: str
    tool_call_id: str
    arguments_raw: str
    arguments: Any = None
    parse_error: str | None = None


class ToolReturned(BaseModel):
    kind: Literal["tool_returned"] = "tool_returned"
    run_id: str
    tool_name: str
    tool_call_id: str
    success: bool


class ToolEvidenceObserved(BaseModel):
    kind: Literal["tool_evidence"] = "tool_evidence"
    run_id: str | None
    tool_name: str
    tool_call_id: str
    content: str
    outcome: str


class UsageObserved(BaseModel):
    kind: Literal["usage"] = "usage"
    run_id: str
    model_name: str
    provider_name: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    requests: int


class RuntimeFailed(BaseModel):
    kind: Literal["runtime_failed"] = "runtime_failed"
    error: str


class RuntimeStopped(BaseModel):
    kind: Literal["runtime_stopped"] = "runtime_stopped"


AkgenticEvalEvent = Annotated[
    MessageObserved
    | ToolCalled
    | ToolReturned
    | ToolEvidenceObserved
    | UsageObserved
    | RuntimeFailed
    | RuntimeStopped,
    Field(discriminator="kind"),
]
