from __future__ import annotations

from ..i18n import t
from .actions import Call, Take
from .cards import is_square
from .signaux import normalize, signal_found  # noqa: F401  (re-exported for the orchestrator)
from .state import Event, GameState


def step(state: GameState, type_: str, pid: int | None, text: str,
         private: str | None = None, **extra) -> None:
    """Adds a step to the timeline, with a snapshot of the center and hands.

    Used for step-by-step replay in the dashboard. Never influences the game.
    """
    state.timeline.append({
        "i": len(state.timeline),
        "round": state.round, "turn": state.turn, "phase": state.phase,
        "type": type_, "pid": pid, "text": text, "private": private,
        "center": [str(c) for c in state.center],
        "hands": {str(p.pid): [str(c) for c in state.hands.get(p.pid, [])]
                  for p in state.players},
        **extra,
    })


def _log(state: GameState, type_: str, pid: int | None, text: str, **extra) -> None:
    ev = Event(state.turn, type_, pid, text, round=state.round)
    state.public_log.append(ev)
    step(state, type_, pid, text, **extra)
    if state.on_event is not None:
        state.on_event(ev, state)


def validate_and_apply_exchange(state: GameState, pid: int, take: Take) -> bool:
    """Validates an exchange against the engine truth. Rejects any illegal move."""
    hand = state.hands[pid]
    if take.from_center not in state.center:
        return False
    if take.discard not in hand:
        return False
    state.center.remove(take.from_center)
    hand.remove(take.discard)
    hand.append(take.from_center)
    state.center.append(take.discard)
    return True


def resolve_discard(state: GameState) -> None:
    """Sweeps the center to the discard pile and distributes 4 new cards (reshuffles if needed)."""
    state.discard.extend(state.center)
    state.center = []
    for _ in range(state.config.center_size):
        if not state.deck:
            if not state.discard:
                break
            state.deck = state.discard
            state.discard = []
            state.rng_cards.shuffle(state.deck)
        if state.deck:
            state.center.append(state.deck.pop())
    state.centers_played += 1


def set_signal(state: GameState, team: int, text: str, trigger: str = "") -> None:
    state.signals[team] = text
    # by default if no explicit trigger, fall back on the convention itself
    state.triggers[team] = trigger or text


def trigger_exploitable(trigger: str) -> bool:
    """Is the trigger specific enough that we dare censor a message based on it?

    Models sometimes produce short and common triggers ('42', 'Spades' - a card game word!).
    Applying them as-is would remove innocent messages. In doubt, we abstain: better to
    let a signal pass than to censor wrongly.
    """
    n = normalize(trigger)
    return bool(n) and (len(n) >= 4 or any(not c.isascii() for c in n))


def emission_without_square(state: GameState, pid: int, message: str) -> bool:
    """Did a player WITHOUT a square slip their team's trigger in their message?

    PURE MEASUREMENT: the engine no longer blocks anything. Emitting one's own signal without
    a square is a legal move - it's bluffing, or a mistake, and in both cases it's data. Blocking
    meant putting training wheels for small models and forbidding a real strategy.
    """
    if is_square(state.hands[pid]):
        return False
    trigger = state.triggers.get(state.team_of(pid), "")
    if not trigger_exploitable(trigger):
        return False
    return signal_found(trigger, message)


def signal_emitted_by_partner(state: GameState, pid: int) -> bool:
    """Has the team's trigger appeared in a partner's message, THIS round?

    An opponent saying the same text by accident does not count. The filter on the round
    is essential: the public chat is never cleared, a signal emitted in round 1
    would otherwise validate a call in round 3.
    """
    partner = state.partner(pid)
    if partner is None:
        return False
    trigger = state.triggers.get(state.team_of(pid), "")
    return any(
        ev.type == "MESSAGE" and ev.pid == partner and ev.round == state.round
        and signal_found(trigger, ev.text)
        for ev in state.public_log
    )


def _episode(state: GameState, pid: int) -> dict | None:
    """The active signaling episode for this player in the current round."""
    for e in reversed(state.episodes):
        if e["round"] == state.round and e["pid"] == pid:
            return e
    return None


def open_episode(state: GameState, pid: int) -> None:
    """A player just completed a square: we open their signaling episode."""
    if _episode(state, pid) is not None:
        return
    state.episodes.append({
        "round": state.round, "pid": pid, "model": state.players[pid].model,
        "square_turn": state.turn, "signal_turn": None, "speech_turn": None,
        "llm_signal_turn": None, "kemps_turn": None, "caught": False, "unmasked": None,
    })


def mark_signal_emitted(state: GameState, pid: int, literal: bool, understood: bool | None = None) -> None:
    """The owner of the square just spoke.

    `literal`: their message contained the trigger word for word. Otherwise we still note
    they spoke (`speech_turn`) - the engine cannot recognize paraphrases, and
    concluding "signal never emitted" would be a lie (cf. "karre" for "kare").
    `understood` (optional, PURE MEASUREMENT): independent LLM judgment, provided by the
    orchestrator - this module remains 100% deterministic and doesn't know what an LLM is;
    we simply accept a ready-made bool. Helps measure paraphrase blindness (`signal_turn` underestimates it).
    """
    e = _episode(state, pid)
    if e is None:
        return
    if e["speech_turn"] is None:
        e["speech_turn"] = state.turn
    if literal and e["signal_turn"] is None:
        e["signal_turn"] = state.turn
    if understood and e.get("llm_signal_turn") is None:
        e["llm_signal_turn"] = state.turn


def resolve_calls(state: GameState, calls: dict[int, Call], order: list[int]) -> None:
    """Resolves the first non-NONE call according to the given order. Can end the game."""
    lang = state.config.lang
    for pid in order:
        call = calls.get(pid)
        if not call or call.kind == "NONE":
            continue
        team = state.team_of(pid)
        name = state.players[pid].name

        if call.kind == "KEMPS":
            partner = state.partner(pid)
            # A call is only canceled if it is UNFOUNDED in the strong sense: the partner does not
            # have a square AND no trigger was spotted. As soon as the partner actually has a
            # square, we resolve normally - the engine cannot recognize a paraphrase
            # ("karre" for "kare"), it must therefore never punish a successful transmission.
            # Rule loyal to Kems: the call is resolved, period. The engine doesn't cancel anything
            # and protects no one from a blind call - it's a bet, and the bet has to be paid.
            # We only note, for measurement, if a signal had actually circulated.
            emitted = signal_emitted_by_partner(state, pid)
            if not emitted:
                state.calls_without_signal.append({
                    "round": state.round, "turn": state.turn, "pid": pid,
                    "model": state.players[pid].model, "winner": is_square(state.hands[partner]),
                })

            success = is_square(state.hands[partner])
            winner = team if success else 1 - team
            state.outcome = {
                "winner_team": winner,
                "reason": t(lang, "kemps_success" if success else "kemps_fail"),
                "caller": pid, "target": partner, "kind": "KEMPS", "success": success,
                # metric: did the partner actually emit the trigger?
                "signal_actually_emitted": emitted,
            }
            _log(state, "CALL", pid, t(lang, "kemps_call_success" if success else "kemps_call_fail", nom=name))
            ep = _episode(state, partner)
            if ep is not None:
                ep["kemps_turn"], ep["caught"] = state.turn, success
            state.finished = True
            # last resort for the team that conceded: unmask the opposing signal
            if success:
                state.comeback_team = 1 - team
            return

        if call.kind == "COUNTER":
            opp = 1 - team
            holders = [p for p in state.team_players(opp) if is_square(state.hands[p])]
            success = len(holders) > 0
            winner = team if success else opp
            state.outcome = {
                "winner_team": winner,
                "reason": t(lang, "counter_success" if success else "counter_fail"),
                "caller": pid, "kind": "COUNTER", "success": success,
            }
            _log(state, "CALL", pid, t(lang, "counter_call_success" if success else "counter_call_fail", nom=name))
            state.finished = True
            return


def resolve_comeback(state: GameState, responses: dict[int, str],
                     responses_found: dict[int, bool] | None = None) -> None:
    """Comeback (riposte): the team that just conceded a KEMPS names the opposing signal.

    If either of its two players unmasks it, they reverse the result and win.
    Arbitration relies on the pre-evaluated results provided (e.g. by an LLM Judge),
    or falls back on literal detection.
    """
    lang = state.config.lang
    team = state.comeback_team
    state.comeback_team = None
    if team is None or state.outcome is None:
        return

    opposing_signal = state.signals.get(1 - team, "")
    opposing_trigger = state.triggers.get(1 - team, "")
    attempts = []
    winner: int | None = None
    for pid in state.team_players(team):
        response = (responses.get(pid) or "").strip()
        
        if responses_found is not None:
            found = responses_found.get(pid, False)
        else:
            found = (signal_found(opposing_signal, response)
                     or signal_found(opposing_trigger, response))
                      
        attempts.append({"pid": pid, "response": response, "found": found})
        _log(state, "RIPOSTE", pid,
             t(lang, "riposte_attempt_unmasked" if found else "riposte_attempt_wrong",
               nom=state.players[pid].name, reponse=response or t(lang, "nothing")))
        if found and winner is None:
            winner = pid

    for e in state.episodes:
        if e["round"] == state.round and state.team_of(e["pid"]) != team:
            e["unmasked"] = winner is not None
    state.outcome["riposte"] = {
        "team": team,
        "opposing_signal": opposing_signal,
        "attempts": attempts,
        "success": winner is not None,
    }
    if winner is not None:
        state.outcome["winner_team"] = team
        state.outcome["reason"] = t(lang, "riposte_success_reason",
                                    nom=state.players[winner].name, signal=opposing_signal)
        _log(state, "SYSTEM", None, t(lang, "riposte_success_log", equipe=team))
    else:
        # NEVER write the real signal here: the chat is public and the match continues
        _log(state, "SYSTEM", None, t(lang, "riposte_fail_log"))


def check_end(state: GameState) -> None:
    """End of current ROUND by exhaustion (no call)."""
    if state.finished:
        return
    cfg = state.config
    if state.round_turn >= cfg.max_turns or state.centers_played >= cfg.max_centers_per_round:
        state.outcome = {"winner_team": None, "reason": t(cfg.lang, "manche_null")}
        state.finished = True


def signal_burned(state: GameState, team: int) -> bool:
    """Was the team's signal just unmasked (successful comeback in the elapsed round)?"""
    if not state.round_history:
        return False
    r = state.round_history[-1].get("riposte")
    return bool(r and r["success"] and r["team"] == 1 - team)


def close_round(state: GameState) -> None:
    """Attributes the point of the round and determines if the match is finished.

    To be called AFTER the optional comeback attempt, as it can reverse the winner.
    """
    lang = state.config.lang
    o = state.outcome or {"winner_team": None, "reason": t(lang, "manche_no_result")}
    winner = o.get("winner_team")
    if winner is not None:
        state.scores[winner] += 1
    o["round"] = state.round
    state.round_history.append(o)

    score = f"{state.scores[0]} - {state.scores[1]}"
    end_reason = o.get("reason", "?")
    _log(state, "SYSTEM", None, t(lang, "manche_end_log", manche=state.round, fin=end_reason, score=score))

    if winner is not None and state.scores[winner] >= state.config.points_to_win:
        state.match_finished = True
        state.match_winner = winner
    elif state.round >= state.config.max_rounds:
        state.match_finished = True
        best = max(state.scores, key=lambda e: state.scores[e])
        state.match_winner = None if state.scores[0] == state.scores[1] else best
