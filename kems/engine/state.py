from __future__ import annotations

from dataclasses import dataclass, field
from random import Random
from typing import Callable

from ..config import Config
from .cards import Card


@dataclass
class Player:
    pid: int
    name: str
    team: int
    model: str


@dataclass
class Event:
    """A line in the global PUBLIC chat (action, message, call, system)."""

    turn: int
    type: str            # SWAP | PASS | MESSAGE | CALL | SWEEP | SYSTEM
    pid: int | None
    text: str
    round: int = 1


@dataclass
class GameState:
    config: Config
    players: list[Player]

    hands: dict[int, list[Card]]          # PRIVATE: pid -> hand
    center: list[Card]                    # public
    deck: list[Card]
    discard: list[Card]

    signals: dict[int, str] = field(default_factory=dict)          # PRIVATE team: team -> signal
    triggers: dict[int, str] = field(default_factory=dict)     # PRIVATE team: literal text to detect
    nego_convergence: dict[int, bool] = field(default_factory=dict)  # MEASUREMENT: agreed signal sealed (True) or locked at limit (False)
    plans: dict[int, str] = field(default_factory=dict)            # PRIVATE player: pid -> plan
    journals: dict[int, list[str]] = field(default_factory=dict)   # PRIVATE player: inner monologue
    team_channels: dict[int, list[str]] = field(default_factory=dict)  # PRIVATE team
    public_log: list[Event] = field(default_factory=list)         # The global chat log

    phase: str = "SETUP"
    turn: int = 0                     # GLOBAL turn number, increasing over the whole match
    round_turn: int = 0              # turn number in the current round
    centers_played: int = 0

    # --- match: sequence of rounds, 1 point per won round ---
    round: int = 1
    scores: dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0})
    match_finished: bool = False
    match_winner: int | None = None
    round_history: list[dict] = field(default_factory=list)   # outcome of each round

    # ORDERED sequence of all steps (public AND private), with center and hand states at each moment.
    # UNIQUE OBSERVABILITY FLOW: dashboard replays it step by step (without heavy fields),
    # debug transcript filters steps holding a decision (`action` present, with prompt and raw response).
    timeline: list[dict] = field(default_factory=list)

    # --- deliverable measurements ---
    # one episode per square formed: square -> signal sent -> caught? -> unmasked?
    episodes: list[dict] = field(default_factory=list)
    # calls made while no signal was detected (blind bet: winner or not)
    calls_without_signal: list[dict] = field(default_factory=list)
    # messages where a player sent their code WITHOUT having a square (bluff or mistake) - pure measurement
    emissions_without_square: list[dict] = field(default_factory=list)
    # how many public messages each player had seen at the time of their last reflection
    seen_at_reflection: dict[int, int] = field(default_factory=dict)

    rng_cards: Random | None = None
    rng_order: Random | None = None

    finished: bool = False
    outcome: dict | None = None

    # optional callback called on each public event (for live printing)
    on_event: Callable | None = None

    # --- helpers ---
    def team_of(self, pid: int) -> int:
        return self.players[pid].team

    def partner(self, pid: int) -> int | None:
        t = self.players[pid].team
        for p in self.players:
            if p.team == t and p.pid != pid:
                return p.pid
        return None

    def team_players(self, team: int) -> list[int]:
        return [p.pid for p in self.players if p.team == team]
