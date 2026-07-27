from __future__ import annotations

from dataclasses import dataclass

from .note import Note


@dataclass(frozen=True)
class Route:
    path: str
    reason: str


def route_note(note: Note) -> Route:
    if note.anchor_type == "fixed":
        return Route(
            path="structural-match",
            reason="fixed anchor_type uses structural causal comparison",
        )
    if note.anchor_type == "contested":
        return Route(
            path="precedent-match",
            reason="contested anchor_type uses precedent retrieval only",
        )
    raise ValueError(f"Unsupported anchor_type: {note.anchor_type}")
