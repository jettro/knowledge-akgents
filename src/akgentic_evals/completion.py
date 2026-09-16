"""Completion policies for Akgentic evaluation conversations."""

from __future__ import annotations

from typing import Protocol

from akgentic_evals.events import MessageObserved


class CompletionPolicy(Protocol):
    """Identify application responses in a normalized event stream."""

    @property
    def reason(self) -> str: ...

    def response_content(self, event: MessageObserved) -> str | None: ...


class MessageResponseCompletion:
    """Complete after messages matching a sender and recipient route."""

    reason = "human_response"

    def __init__(
        self,
        *,
        recipient: str = "@Human",
        sender: str | None = None,
    ) -> None:
        self._recipient = recipient
        self._sender = sender

    def response_content(self, event: MessageObserved) -> str | None:
        if (
            event.recipient == self._recipient
            and event.sender != self._recipient
            and (self._sender is None or event.sender == self._sender)
            and event.content
        ):
            return event.content
        return None
