from __future__ import annotations

from dataclasses import dataclass

from .cards import Card


@dataclass
class Take:
    """1-for-1 exchange: take `from_center` from the center, discard `discard` from one's hand."""

    from_center: Card
    discard: Card


@dataclass
class Pass:
    """Do not take anything this subturn."""


@dataclass
class Call:
    kind: str  # "KEMPS" | "COUNTER" | "NONE"


@dataclass
class Nego:
    """A negotiation turn: what the player says, proposes, and the exact trigger kept."""

    message: str
    proposition: str | None
    trigger: str | None      # the literal text the engine will have to detect
    agree: bool
    plan: str | None = None      # personal plan / memory (optional)

