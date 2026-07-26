from __future__ import annotations

from dataclasses import dataclass, field

from .cards import Card, is_square
from .state import Event, GameState


@dataclass
class PlayerView:
    """What a player has the RIGHT to see. Safety boundary: no private info of others."""

    pid: int
    name: str
    team: int
    partner_name: str

    my_hand: list[Card]
    has_square: bool                     # set by referee (anti-hallucination)
    my_signal: str
    my_trigger: str                      # the LITERAL trigger pinned by the engine (anti-confabulation)
    my_plan: str
    my_team_chat: list[str]
    my_journal: list[str]               # inner monologue, invisible to ALL others

    center: list[Card]                   # public
    global_chat: list[Event]             # bounded window of the public chat

    scores: dict[int, int] = field(default_factory=dict)   # match score
    round: int = 1                                         # current round number
    round_history: list[dict] = field(default_factory=list)  # history of elapsed rounds

    nego_proposal: str = ""              # negotiation: the candidate signal under discussion
    nego_trigger: str = ""              # negotiation: the trigger on the table (must re-write to seal)
    nego_remaining: int = 0               # negotiation: exchanges remaining before locking at limit
    my_reflection: str = ""               # the private reflection the player just wrote
    opponents: list[str] = field(default_factory=field)   # public: names of the opposing team


def view_for(state: GameState, pid: int,
             nego_proposal: str = "", full_chat: bool = False,
             reflection: str = "", nego_trigger: str = "",
             nego_remaining: int = 0) -> PlayerView:
    team = state.team_of(pid)
    window = len(state.public_log) if full_chat else state.config.chat_window
    partner_id = state.partner(pid)
    partner_name = state.players[partner_id].name if partner_id is not None else "?"
    return PlayerView(
        pid=pid,
        name=state.players[pid].name,
        team=team,
        partner_name=partner_name,
        my_hand=list(state.hands[pid]),
        has_square=is_square(state.hands[pid]),
        my_signal=state.signals.get(team, ""),
        my_trigger=state.triggers.get(team, ""),
        my_plan=state.plans.get(pid, ""),
        my_team_chat=list(state.team_channels.get(team, [])),
        my_journal=list(state.journals.get(pid, [])),
        center=list(state.center),
        global_chat=list(state.public_log[-window:]),
        scores=dict(state.scores),
        round=state.round,
        round_history=list(state.round_history),
        nego_proposal=nego_proposal,
        nego_trigger=nego_trigger,
        nego_remaining=nego_remaining,
        my_reflection=reflection,
        opponents=[p.name for p in state.players if p.team != team],
    )
