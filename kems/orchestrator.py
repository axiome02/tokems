from __future__ import annotations

import hashlib
from random import Random

from .config import Config
from .engine import rules
from .engine.actions import Call, Take
from .engine.cards import build_deck, is_square
from .engine.signaux import NO_SIGNAL, normalize
from .engine.state import Event, GameState, Player
from .engine.views import view_for
from .i18n import t


# Neutral identifiers: a first name carries connotations that influence models.
# Translated according to the game language: these names are written word-for-word in the prompts.
def _name(pid: int, lang: str = "en") -> str:
    return t(lang, "player_label", n=pid + 1)


def _derive(master: int, label: str) -> int:
    h = hashlib.sha256(f"{master}:{label}".encode()).hexdigest()
    return int(h[:16], 16)


def setup(config: Config, models: list[str]) -> GameState:
    rng_cards = Random(config.seed_cards if config.seed_cards is not None
                       else _derive(config.master_seed, "cards"))
    rng_order = Random(config.seed_order if config.seed_order is not None
                       else _derive(config.master_seed, "order"))

    players = [
        Player(pid=i, name=_name(i, config.lang), team=i % 2, model=models[i])
        for i in range(config.num_players)
    ]

    deck = build_deck(config.num_ranks)
    rng_cards.shuffle(deck)

    hands = {p.pid: [deck.pop() for _ in range(config.hand_size)] for p in players}
    center = [deck.pop() for _ in range(config.center_size)]

    state = GameState(
        config=config,
        players=players,
        hands=hands,
        center=center,
        deck=deck,
        discard=[],
        signals={},
        plans={p.pid: "" for p in players},
        journals={p.pid: [] for p in players},
        team_channels={0: [], 1: []},
        public_log=[],
        rng_cards=rng_cards,
        rng_order=rng_order,
    )
    state.public_log.append(
        Event(0, "SYSTEM", None,
              t(config.lang, "start_game", seed=config.master_seed, rangs=config.num_ranks))
    )
    return state


def new_round(state: GameState) -> None:
    """Redistributes everything for the next round. The public chat is never cleared."""
    state.round += 1
    state.turn += 1                 # the new deal already belongs to the first turn of the round
    state.round_turn = 1
    state.centers_played = 0
    state.finished = False
    state.outcome = None
    state.comeback_team = None

    deck = build_deck(state.config.num_ranks)
    state.rng_cards.shuffle(deck)
    state.hands = {p.pid: [deck.pop() for _ in range(state.config.hand_size)] for p in state.players}
    state.center = [deck.pop() for _ in range(state.config.center_size)]
    state.deck = deck
    state.discard = []
    rules._log(state, "SYSTEM", None,
               t(state.config.lang, "new_deal", manche=state.round,
                 s0=state.scores[0], s1=state.scores[1]))


def _order(state: GameState) -> list[int]:
    order = [p.pid for p in state.players]
    state.rng_order.shuffle(order)
    return order


def _extras_decision(view, agent, action_str: str) -> dict:
    """Extras attached to the timeline step holding a DECISION: the decided action, the hand
    of the decision-maker at that moment, and the raw LLM exchange (prompt, response).
    UNIQUE observability flow: debug transcript filters the timeline on the presence of `action`
    (the dashboard ignores heavy fields)."""
    io = getattr(agent, "last_io", None)
    return {
        "action": action_str,
        "main": [str(c) for c in view.my_hand],
        "carre": view.has_square,
        "prompt_user": io[1] if io else None,
        "reponse_brute": io[2] if io else None,
    }


def negotiation(state: GameState, agents: dict, teams: tuple[int, ...] | None = None) -> None:
    """Alternating discussion A<->B per team to converge towards the best signal.

    Each turn, the player sees the running dialogue + the proposal on the table; they
    propose/refine, or lock (AGREE: YES) the proposal made by their teammate.
    We stop as soon as an agreement is made on the OTHER player's proposal (guarantees at
    least one back-and-forth), otherwise at max_negotiation_turns (freezes the last proposal).

    Notarized sealing (anti-confabulation): an agreement - explicit or
    tacit - only closes the negotiation if (a) the trigger on the table is EXPLOITABLE
    (concrete, not meta-policy) and (b) the agreeing player RE-WRITES this trigger
    (read-back: both players have independently written the same literal string -
    shared understanding is proven, not assumed). The engine does not dictate the content:
    it refuses to authenticate a contract without its essential clause. Without sealing,
    we freeze as before and `state.nego_convergence[team] = False` measures it.
    """
    state.phase = "NEGOTIATION"
    for team in teams if teams is not None else (0, 1):
        players = state.team_players(team)
        proposal = ""
        trigger = ""
        proposer: int | None = None  # who made the proposal currently on the table
        sealed = False
        for nt in range(state.config.max_negotiation_turns):
            pid = players[nt % len(players)]
            view = view_for(state, pid, nego_proposal=proposal,
                            nego_trigger=trigger,
                            nego_remaining=state.config.max_negotiation_turns - nt)
            n = agents[pid].negotiate(view)
            name = state.players[pid].name
            if n.message:
                state.team_channels[team].append(f"{name}: {n.message}")
            agree_word = t(state.config.lang, "yes_word" if n.agree else "no_word")
            rules.step(state, "NEGOTIATION", pid,
                       t(state.config.lang, "negotiating", nom=name), private=n.message,
                       proposition=n.proposition, declencheur=n.trigger, accord=n.agree,
                       **_extras_decision(view, agents[pid],
                                          f"MESSAGE='{n.message}' PROPOSITION='{n.proposition}' "
                                          f"DECLENCHEUR='{n.trigger}' ACCORD={agree_word}"))
            # Agreement only valid on a proposal made by the teammate - explicit (AGREE: YES)
            # or tacit: copying word-for-word the proposal on the table is keeping it.
            # Without this second branch, models exchange the same sentence until max_negotiation_turns.
            echo = bool(n.proposition and proposal
                        and normalize(n.proposition) == normalize(proposal))
            # read-back: the agreeing player re-writes the trigger on the table identically
            readback = bool(trigger and n.trigger
                            and normalize(n.trigger) == normalize(trigger))
            if ((n.agree or echo) and proposal and proposer is not None
                    and proposer != pid and readback
                    and rules.trigger_exploitable(trigger)):
                sealed = True
                break
            if n.proposition:
                proposal, proposer = n.proposition, pid
                trigger = n.trigger or ""
        state.nego_convergence[team] = sealed
        rules.set_signal(state, team, proposal or NO_SIGNAL, trigger)


def debriefing_phase(state: GameState, agents: dict) -> None:
    """Debriefing and code rotation/adaptation phase at the end of a round (max 4 turns)."""
    state.phase = "DEBRIEFING"
    lang = state.config.lang
    
    for team in (0, 1):
        # We start from an empty discussion channel for this inter-round debriefing
        burned = rules.signal_burned(state, team)
        state.team_channels[team] = []
        if burned:
            state.team_channels[team].append(t(state.config.lang, "signal_burned_notice"))
            
        players = state.team_players(team)
        
        # Current signal serves as base
        proposal = state.signals.get(team, "")
        trigger = state.triggers.get(team, "")
        proposer: int | None = None
        sealed = False
        
        # Debriefing in 4 turns maximum (2 turns of speech per player)
        max_debriefing_turns = 4
        for nt in range(max_debriefing_turns):
            pid = players[nt % len(players)]
            view = view_for(state, pid, nego_proposal=proposal,
                            nego_trigger=trigger,
                            nego_remaining=max_debriefing_turns - nt)
            
            n = agents[pid].debrief(view)
            name = state.players[pid].name
            if n.message:
                state.team_channels[team].append(f"{name}: {n.message}")
            if n.plan:
                state.plans[pid] = n.plan
                
            agree_word = t(lang, "yes_word" if n.agree else "no_word")
            rules.step(state, "DEBRIEFING", pid,
                       t(lang, "negotiating", nom=name), private=n.message,
                       proposition=n.proposition, declencheur=n.trigger, accord=n.agree,
                       **_extras_decision(view, agents[pid],
                                          f"MESSAGE='{n.message}' PROPOSITION='{n.proposition}' "
                                          f"DECLENCHEUR='{n.trigger}' ACCORD={agree_word} PLAN='{n.plan}'"))
            
            echo = bool(n.proposition and proposal
                        and normalize(n.proposition) == normalize(proposal))
            readback = bool(trigger and n.trigger
                            and normalize(n.trigger) == normalize(trigger))
            if ((n.agree or echo) and proposal and proposer is not None
                    and proposer != pid and readback
                    and rules.trigger_exploitable(trigger)):
                sealed = True
                break
            if n.proposition:
                proposal, proposer = n.proposition, pid
                trigger = n.trigger or ""
                
        # We update the signal
        rules.set_signal(state, team, proposal or NO_SIGNAL, trigger)


def exchange_phase(state: GameState, agents: dict) -> None:
    state.phase = "EXCHANGE"
    cfg = state.config
    num_players = cfg.num_players
    consecutive_passes = 0
    st = 0
    order = _order(state)
    while st < cfg.max_subturns_per_center:
        for pid in order:
            name = state.players[pid].name
            if is_square(state.hands[pid]):
                # episode opened in silence: chat is public, a square is private.
                # The player decides whether to keep or break it.
                rules.open_episode(state, pid)
            view = view_for(state, pid)
            action = agents[pid].decide_card(view)
            if isinstance(action, Take):
                if rules.validate_and_apply_exchange(state, pid, action):
                    rules._log(state, "SWAP", pid,
                               t(state.config.lang, "takes_discards", nom=name,
                                 prise=str(action.from_center), repose=str(action.discard)),
                               prise=str(action.from_center), repose=str(action.discard),
                               **_extras_decision(view, agents[pid],
                                                  f"TAKE {action.from_center} DISCARD {action.discard}"))
                    consecutive_passes = 0
                    if is_square(state.hands[pid]):
                        rules.open_episode(state, pid)
                else:
                    rules._log(state, "SYSTEM", pid, t(state.config.lang, "illegal_exchange", nom=name),
                               **_extras_decision(view, agents[pid],
                                                  f"ILLEGAL {action.from_center}/{action.discard} -> PASS"))
                    consecutive_passes += 1
            else:
                rules._log(state, "PASS", pid, t(state.config.lang, "passes", nom=name),
                           **_extras_decision(view, agents[pid], "PASS"))
                consecutive_passes += 1
            
            if consecutive_passes >= num_players:
                break
        if consecutive_passes >= num_players:
            break
        st += 1
    rules.resolve_discard(state)
    rules._log(state, "SWEEP", None,
               t(state.config.lang, "center_swept",
                 cartes=" ".join(str(c) for c in state.center)))


def _recent_text(state: GameState, limit: int = 8) -> str:
    """Public chat window of the current round, for the LLM judge (measurement)."""
    conv = [ev for ev in state.public_log
            if ev.type in ("MESSAGE", "CALL") and ev.round == state.round]
    conv = conv[-limit:]
    return "\n".join(ev.text for ev in conv)


def _judge_kemps_transmission(state: GameState, agents: dict) -> None:
    """Independent LLM judgment (PURE MEASUREMENT, never affects results): did the calling team's
    signal actually circulate, beyond literal word-for-word matching?
    """
    if not state.config.eval_signals:
        return
    o = state.outcome
    if not o or o.get("kind") != "KEMPS":
        return
    team = state.team_of(o["caller"])
    convention = state.signals.get(team, "")
    trigger = state.triggers.get(team, "")
    text = _recent_text(state)
    if text:
        try:
            evaluator = agents.get("evaluateur")
            if evaluator is not None:
                o["signal_actually_emitted_llm"] = evaluator.juger_signal(convention, trigger, text)
        except Exception:
            pass


def discussion_phase(state: GameState, agents: dict) -> None:
    state.phase = "DISCUSSION"
    # multiple speech passes per turn: first pass exposes signals, next let partner react in stride
    for _ in range(state.config.discussion_turns):
        order = _order(state)
        calls: dict[int, Call] = {}
        for pid in order:
            # 1) player reflects privately
            journal = state.journals.setdefault(pid, [])
            seen_events = sum(1 for ev in state.public_log if ev.type in ("MESSAGE", "CALL"))
            if journal and not is_square(state.hands[pid]) and seen_events == state.seen_at_reflection.get(pid):
                reflection = journal[-1]
            else:
                view_reflection = view_for(state, pid)
                reflection = agents[pid].reflect(view_reflection)
                journal.append(reflection)
                state.seen_at_reflection[pid] = seen_events
                rules.step(state, "REFLEXION", pid,
                           t(state.config.lang, "reflecting", nom=state.players[pid].name),
                           private=reflection,
                           **_extras_decision(view_reflection, agents[pid], reflection))

            # 2) player speaks in public, private reflection in view
            view = view_for(state, pid, reflection=reflection)
            msg, call, plan = agents[pid].decide_discussion(view)
            call = call if isinstance(call, Call) else Call("NONE")
            extras = _extras_decision(view, agents[pid],
                                      f"MESSAGE='{msg}' CALL={call.kind} PLAN='{plan}'")
            if plan:
                state.plans[pid] = plan
            if msg and rules.emission_without_square(state, pid, msg):
                # legal: bluff or mistake, not censored. Noted for measurement without writing to public chat.
                state.emissions_without_square.append({
                    "round": state.round, "turn": state.turn, "pid": pid,
                    "model": state.players[pid].model,
                })
            if msg:
                rules._log(state, "MESSAGE", pid,
                           t(state.config.lang, "says", nom=state.players[pid].name, msg=msg),
                           **extras)
                if is_square(state.hands[pid]):
                    team = state.team_of(pid)
                    trigger = state.triggers.get(team, "")
                    literal = rules.signal_found(trigger, msg)
                    try:
                        evaluator = agents.get("evaluateur")
                        if evaluator is not None and state.config.eval_signals:
                            understood = evaluator.judge_signal(
                                state.signals.get(team, ""), trigger, _recent_text(state))
                        else:
                            understood = None
                    except Exception:
                        understood = None
                    rules.mark_signal_emitted(state, pid, literal, understood)
            else:
                rules.step(state, "DISCUSSION", pid, "", private=None, **extras)
            calls[pid] = call
        rules.resolve_calls(state, calls, order)
        if state.finished:
            _judge_kemps_transmission(state, agents)
            return


def riposte_phase(state: GameState, agents: dict) -> None:
    """Last resort comeback: the team that just conceded a KEMPS attempts to name the opposing signal.

    Its 2 players answer; a single correct answer reverses the match.
    """
    state.phase = "RIPOSTE"
    team = state.comeback_team
    rules._log(state, "SYSTEM", None, t(state.config.lang, "riposte_intro", equipe=team))
    responses: dict[int, str] = {}
    for pid in state.team_players(team):
        view = view_for(state, pid, full_chat=True)
        guess = agents[pid].guess_signal(view)
        responses[pid] = guess.response
        rules.step(state, "RIPOSTE", pid,
                   t(state.config.lang, "riposte_attempt", nom=state.players[pid].name),
                   private=guess.response,
                   **_extras_decision(view, agents[pid], f"SIGNAL_ADVERSE='{guess.response}'"))

    # Semantic LLM Judge
    responses_found = {}
    evaluator = agents.get("evaluateur")
    opposing_signal = state.signals.get(1 - team, "")
    opposing_trigger = state.triggers.get(1 - team, "")
    for pid, response in responses.items():
        if not response.strip():
            responses_found[pid] = False
            continue
        try:
            if evaluator is not None:
                responses_found[pid] = evaluator.judge_comeback(opposing_signal, opposing_trigger, response)
            else:
                raise ValueError("No dedicated evaluator agent configured")
        except Exception:
            # Deterministic fallback on API error (quota, timeout...)
            from .engine import signaux
            responses_found[pid] = (signaux.signal_found(opposing_signal, response)
                                     or signaux.signal_found(opposing_trigger, response))

    rules.resolve_comeback(state, responses, responses_found)


def play_manche(state: GameState, agents: dict) -> None:
    while not state.finished:
        exchange_phase(state, agents)
        if state.finished:
            break
        discussion_phase(state, agents)
        if state.comeback_team is not None:
            riposte_phase(state, agents)
        rules.check_end(state)
        if not state.finished:
            state.turn += 1
            state.round_turn += 1


def play_game(config: Config, models: list[str], agents: dict, on_event=None) -> GameState:
    """Plays a MATCH: successive rounds until `points_to_win`."""
    state = setup(config, models)
    if on_event is not None:
        for ev in state.public_log:
            on_event(ev, state)
        state.on_event = on_event

    negotiation(state, agents)      # happens at turn 0, before any deal
    state.turn = state.round_turn = 1
    while True:
        play_manche(state, agents)
        rules.close_round(state)
        if state.match_finished:
            break
        debriefing_phase(state, agents)
        new_round(state)
    return state
