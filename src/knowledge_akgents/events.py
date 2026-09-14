"""Bridge orchestrator events onto a simple publish callback.

An ``EventSubscriber`` runs on actor threads, so ``publish`` must be safe to call from a
non-async thread — the backend passes a callback that hands off to the asyncio loop.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from akgentic.core import EventSubscriber
from akgentic.core.messages import Message
from akgentic.core.messages.orchestrator import ErrorMessage, EventMessage, SentMessage

# LLM events live in akgentic-llm; guard so this bridge never hard-fails.
LlmMessageEvent: type | None
LlmUsageEvent: type | None
ToolCallEvent: type | None
ToolReturnEvent: type | None
try:
    from akgentic.llm import (
        LlmMessageEvent as _LlmMessageEvent,
    )
    from akgentic.llm import (
        LlmUsageEvent as _LlmUsageEvent,
    )
    from akgentic.llm import (
        ToolCallEvent as _ToolCallEvent,
    )
    from akgentic.llm import (
        ToolReturnEvent as _ToolReturnEvent,
    )

    LlmMessageEvent = _LlmMessageEvent
    LlmUsageEvent = _LlmUsageEvent
    ToolCallEvent = _ToolCallEvent
    ToolReturnEvent = _ToolReturnEvent
except Exception:  # pragma: no cover - defensive
    LlmMessageEvent = None
    LlmUsageEvent = None
    ToolCallEvent = None
    ToolReturnEvent = None

Publish = Callable[[dict[str, Any]], None]

_EXCLUDED_SENDERS = {"Orchestrator", "@Orchestrator"}


class WebEventBridge(EventSubscriber):
    """Forwards relevant team traffic to the web layer as plain dicts."""

    def __init__(self, publish: Publish) -> None:
        self._publish = publish

    # --- EventSubscriber protocol -------------------------------------------------
    def set_restoring(self, team_id: Any, restoring: bool) -> None:  # noqa: FBT001
        pass

    def on_stop(self, team_id: Any) -> None:
        pass

    def on_stop_request(self, team_id: Any) -> None:
        pass

    def on_message(self, message: Message) -> None:
        sender = getattr(getattr(message, "sender", None), "name", None)
        if sender in _EXCLUDED_SENDERS:
            return
        if isinstance(message, SentMessage):
            self._handle_sent(message, sender)
        elif isinstance(message, EventMessage):
            self._handle_event(message, sender)
        elif isinstance(message, ErrorMessage):
            self._publish(
                {
                    "kind": "error",
                    "sender": sender,
                    "content": (
                        f"{message.content_type or 'Error'}: {message.content}"
                    ).strip(),
                }
            )

    # --- handlers -----------------------------------------------------------------
    def _handle_sent(self, message: SentMessage, sender: str | None) -> None:
        msg = message.message
        if not hasattr(msg, "content"):
            return
        recipient = getattr(getattr(message, "recipient", None), "name", None)
        content = getattr(msg, "content", "")
        self._publish(
            {
                "kind": "message",
                "sender": sender,
                "recipient": recipient,
                "type": getattr(msg, "type", ""),
                "content": content,
            }
        )

    def _handle_event(self, message: EventMessage, sender: str | None) -> None:
        event = getattr(message, "event", None)
        if ToolCallEvent is not None and isinstance(event, ToolCallEvent):
            tool_name = getattr(event, "tool_name", "")
            args_str = _stringify(getattr(event, "arguments", ""))
            self._publish(
                {
                    "kind": "tool_call",
                    "sender": sender,
                    "tool": tool_name,
                    "run_id": getattr(event, "run_id", ""),
                    "tool_call_id": getattr(event, "tool_call_id", ""),
                    "arguments": args_str,
                }
            )
        elif ToolReturnEvent is not None and isinstance(event, ToolReturnEvent):
            self._publish(
                {
                    "kind": "tool_return",
                    "sender": sender,
                    "tool": getattr(event, "tool_name", ""),
                    "run_id": getattr(event, "run_id", ""),
                    "tool_call_id": getattr(event, "tool_call_id", ""),
                    "success": bool(getattr(event, "success", False)),
                }
            )
        elif LlmUsageEvent is not None and isinstance(event, LlmUsageEvent):
            self._publish(
                {
                    "kind": "llm_usage",
                    "sender": sender,
                    "run_id": getattr(event, "run_id", ""),
                    "model_name": getattr(event, "model_name", ""),
                    "provider_name": getattr(event, "provider_name", ""),
                    "input_tokens": getattr(event, "input_tokens", 0),
                    "output_tokens": getattr(event, "output_tokens", 0),
                    "cache_read_tokens": getattr(event, "cache_read_tokens", 0),
                    "cache_write_tokens": getattr(event, "cache_write_tokens", 0),
                    "requests": getattr(event, "requests", 0),
                }
            )
        elif LlmMessageEvent is not None and isinstance(event, LlmMessageEvent):
            self._publish_tool_evidence(getattr(event, "message", None), sender)

    def _publish_tool_evidence(self, message: Any, sender: str | None) -> None:
        try:
            from pydantic_ai.messages import ModelRequest, ToolReturnPart
        except ImportError:  # pragma: no cover - application dependency
            return
        if not isinstance(message, ModelRequest):
            return
        for part in message.parts:
            if not isinstance(part, ToolReturnPart):
                continue
            self._publish(
                {
                    "kind": "tool_evidence",
                    "sender": sender,
                    "run_id": message.run_id,
                    "tool": part.tool_name,
                    "tool_call_id": part.tool_call_id,
                    "content": _stringify(part.content),
                    "outcome": part.outcome,
                }
            )


def _stringify(value: Any) -> str:
    try:
        return str(value)
    except Exception:  # pragma: no cover - defensive
        return "<unrepresentable>"
