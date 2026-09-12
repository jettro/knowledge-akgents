"""Bridge orchestrator events onto a simple publish callback.

An ``EventSubscriber`` runs on actor threads, so ``publish`` must be safe to call from a
non-async thread — the backend passes a callback that hands off to the asyncio loop.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from akgentic.core import EventSubscriber
from akgentic.core.messages import Message
from akgentic.core.messages.orchestrator import EventMessage, SentMessage

# ToolCallEvent lives in akgentic-llm; guard so import never hard-fails.
ToolCallEvent: type | None
try:
    from akgentic.llm import ToolCallEvent as _ToolCallEvent

    ToolCallEvent = _ToolCallEvent
except Exception:  # pragma: no cover - defensive
    ToolCallEvent = None

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
                    "arguments": args_str,
                }
            )


def _stringify(value: Any) -> str:
    try:
        return str(value)
    except Exception:  # pragma: no cover - defensive
        return "<unrepresentable>"
