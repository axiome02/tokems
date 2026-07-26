from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Config:
    """All configuration options for the game (see CLAUDE.md, improvement #1)."""

    num_ranks: int = 10                 # cards 1..num_ranks (default 1-10 = 40 cards, squares slower)
    num_players: int = 4
    hand_size: int = 4
    center_size: int = 4

    # format: a MATCH is a sequence of rounds, each round win is worth 1 point
    points_to_win: int = 3
    max_rounds: int = 9               # cost bound: beyond this, the match stops at current score

    # cost/length bounds (per round)
    max_subturns_per_center: int = 3
    max_centers_per_round: int = 12
    max_turns: int = 8                 # ~5 turns are needed between signaling and KEMPS
    max_negotiation_turns: int = 10    # max exchange turns A<->B per team to agree on the signal
    discussion_turns: int = 2          # speech turns per discussion phase (everyone speaks N times)

    # how many of the last public events are sent to the LLM
    chat_window: int = 40

    master_seed: int = 0
    # optional overrides: by default both streams are derived from master_seed, but they
    # can be fixed separately (e.g. to replay the same deal with a different play order)
    seed_cards: int | None = None
    seed_order: int | None = None

    # game language: LLM prompts + public events + transcript. "en" or "fr".
    # Default "en" (public benchmark standard); no recalibration has been done for "fr"
    # since multilingual support was added (2026-07-22): reference measurements remain in French.
    lang: str = "en"

    # Optional: Semantic evaluation of the signal transmission via LLM
    eval_signals: bool = True      # if True, calls an LLM judge to evaluate the transmission
    evaluator_model: str | None = None  # specifies the model/provider of the judge (e.g. "gpt-4o")
