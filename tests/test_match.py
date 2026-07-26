from kems.config import Config
from kems.engine import rules
from kems.engine.actions import Call
from kems.engine.cards import SUITS, Card
from kems.orchestrator import new_round, setup


def _state(**cfg):
    return setup(Config(master_seed=1, **cfg), ["bot"] * 4)


def _win_round(state, team):
    """The given team wins the current round via a successful KEMPS."""
    caller = state.team_players(team)[0]
    partner = state.partner(caller)
    state.hands[partner] = [Card(5, c) for c in SUITS]
    rules.set_signal(state, team, "convention", trigger="the cat is sleeping")
    rules._log(state, "MESSAGE", partner, "« hey, the cat is sleeping already »")   # arm the call
    rules.resolve_calls(state, {caller: Call("KEMPS")}, [caller])
    state.comeback_team = None          # ignore comeback here
    rules.close_round(state)


def test_point_allocated_and_match_not_finished():
    state = _state()
    _win_round(state, 0)
    assert state.scores == {0: 1, 1: 0}
    assert state.match_finished is False
    assert len(state.round_history) == 1


def test_match_won_at_three_points():
    state = _state()
    for _ in range(3):
        if state.match_finished:
            break
        _win_round(state, 0)
        if not state.match_finished:
            new_round(state)
    assert state.scores[0] == 3
    assert state.match_finished is True
    assert state.match_winner == 0


def test_drawn_round_gives_no_point():
    state = _state(max_turns=1)
    state.round_turn = 1
    rules.check_end(state)
    rules.close_round(state)
    assert state.scores == {0: 0, 1: 0}
    assert state.match_finished is False


def test_max_rounds_stops_match_at_score():
    state = _state(max_rounds=2)
    _win_round(state, 0)
    new_round(state)
    _win_round(state, 1)
    assert state.match_finished is True
    assert state.match_winner is None      # 1-1 -> draw
    assert state.scores == {0: 1, 1: 1}


def test_new_round_redistributes_without_clearing_chat():
    state = _state()
    _win_round(state, 0)
    hands_before = {p: list(h) for p, h in state.hands.items()}
    lines_before = len(state.public_log)
    new_round(state)
    assert state.round == 2
    # new deal already belongs to turn 1 of new round
    assert state.round_turn == 1 and state.centers_played == 0
    assert state.finished is False and state.outcome is None
    assert state.hands != hands_before
    assert all(len(h) == 4 for h in state.hands.values())
    assert len(state.public_log) > lines_before      # public chat is never cleared


def test_signal_burned_only_after_successful_comeback():
    state = _state()
    rules.set_signal(state, 0, "☀️")
    state.hands[2] = [Card(5, c) for c in SUITS]
    rules._log(state, "MESSAGE", 2, "Player 3: « nice evening ☀️ »")   # arm the call
    rules.resolve_calls(state, {0: Call("KEMPS")}, [0])
    rules.resolve_comeback(state, {1: "the emoji ☀️", 3: "nothing"})
    rules.close_round(state)
    assert rules.signal_burned(state, 0) is True      # team 0 got unmasked
    assert rules.signal_burned(state, 1) is False
    assert state.scores == {0: 0, 1: 1}              # comeback reversed the round winner


def test_signal_not_burned_if_comeback_fails():
    state = _state()
    rules.set_signal(state, 0, "☀️")
    state.hands[2] = [Card(5, c) for c in SUITS]
    rules._log(state, "MESSAGE", 2, "Player 3: « nice evening ☀️ »")   # arm the call
    rules.resolve_calls(state, {0: Call("KEMPS")}, [0])
    rules.resolve_comeback(state, {1: "the weather", 3: "nothing"})
    rules.close_round(state)
    assert rules.signal_burned(state, 0) is False
    assert state.scores == {0: 1, 1: 0}


def test_failed_comeback_does_not_reveal_signal_in_public_chat():
    state = _state()
    rules.set_signal(state, 0, "pineapple")
    state.hands[2] = [Card(5, c) for c in SUITS]
    rules.resolve_calls(state, {0: Call("KEMPS")}, [0])
    rules.resolve_comeback(state, {1: "banana", 3: "cherry"})
    # match continues: real signal must not appear anywhere in the chat
    assert not any("pineapple" in ev.text for ev in state.public_log)


def test_drawn_round_does_not_loop_if_max_rounds_is_1():
    state = _state(max_turns=6, max_rounds=1, points_to_win=1)
    state.round_turn = 6
    rules.check_end(state)
    rules.close_round(state)
    assert state.match_finished is True
    assert state.match_winner is None


def test_new_deal_has_turn_number_of_starting_turn():
    state = _state()
    state.turn = 4
    _win_round(state, 0)
    new_round(state)
    deal = state.public_log[-1]  # new_round() only logs this single event
    assert deal.turn == 5 and deal.round == 2
