from __future__ import annotations

from dataclasses import dataclass

SUITS = ["♠", "♥", "♦", "♣"]  # spades, hearts, diamonds, clubs


@dataclass(frozen=True)
class Card:
    rank: int          # 1..num_ranks
    suit: str       # one of SUITS

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"


def build_deck(num_ranks: int) -> list[Card]:
    return [Card(r, c) for r in range(1, num_ranks + 1) for c in SUITS]


def is_square(hand: list[Card]) -> bool:
    """True if the hand is a square: 4 cards of the same rank."""
    return len(hand) == 4 and len({c.rank for c in hand}) == 1


def square_rank(hand: list[Card]) -> int | None:
    return hand[0].rank if is_square(hand) else None
