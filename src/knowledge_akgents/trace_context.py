"""Propagate Python context variables across Akgentic actor threads."""

from __future__ import annotations

from collections.abc import Callable
from contextvars import Context, copy_context
from typing import Any, override

from akgentic.agent import BaseAgent, HumanProxy
from akgentic.core import ActorAddress
from akgentic.core.messages.message import Message

_CONTEXT_ATTRIBUTE = "_knowledge_akgents_context"


def attach_message_context(message: Message) -> None:
    """Capture the current context once, before a message crosses a thread boundary."""
    if not isinstance(getattr(message, _CONTEXT_ATTRIBUTE, None), Context):
        setattr(message, _CONTEXT_ATTRIBUTE, copy_context())


def run_in_message_context[T](message: Any, callback: Callable[[], T]) -> T:
    """Run a message handler in a fresh copy of its captured context."""
    context = getattr(message, _CONTEXT_ATTRIBUTE, None)
    if not isinstance(context, Context):
        return callback()
    return context.copy().run(callback)


class TraceContextBaseAgent(BaseAgent):
    """BaseAgent that carries context variables with in-process actor messages."""

    @override
    def send(self, recipient: ActorAddress | None, message: Any) -> Any:
        if isinstance(message, Message):
            attach_message_context(message)
        return super().send(recipient, message)

    @override
    def on_receive(self, message: Any) -> Any:
        handler = super().on_receive
        return run_in_message_context(message, lambda: handler(message))


class TraceContextHumanProxy(HumanProxy):
    """HumanProxy that preserves context when forwarding team messages."""

    @override
    def send(self, recipient: ActorAddress | None, message: Any) -> Any:
        if isinstance(message, Message):
            attach_message_context(message)
        return super().send(recipient, message)

    @override
    def on_receive(self, message: Any) -> Any:
        handler = super().on_receive
        return run_in_message_context(message, lambda: handler(message))
