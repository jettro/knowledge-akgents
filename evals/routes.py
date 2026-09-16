"""Knowledge Akgents message-route policy used by evaluation scenarios."""

from __future__ import annotations


def managed_route(*actors: str) -> tuple[tuple[str, str], ...]:
    """Build the expected route for turns coordinated by the manager."""
    return tuple(
        edge
        for actor in actors
        for edge in (
            ("@Human", "@Manager"),
            ("@Manager", actor),
            (actor, "@Manager"),
            ("@Manager", "@Human"),
        )
    )


def direct_route(actor: str) -> tuple[tuple[str, str], ...]:
    """Build the expected route for a directly addressed specialist."""
    return (("@Human", actor), (actor, "@Human"))
