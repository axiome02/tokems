"""Verifiable KEMPS and signaling episodes checks."""
from kems.config import Config
from kems.engine import rules
from kems.engine.actions import Call
from kems.engine.cards import SUITS, Card
from kems.orchestrator import setup


def _state():
    state = setup(Config(master_seed=1), ["bot"] * 4)
    rules.set_signal(state, 0, "the phrase of the cat", trigger="the cat is sleeping")
    rules.set_signal(state, 1, "other", trigger="fan")
    state.hands[2] = [Card(5, c) for c in SUITS]      # partner of player 0 has a square
    return state


def _emettre(state, pid=2):
    """The square holder slips their trigger in a public message."""
    rules._log(state, "MESSAGE", pid, f"Player {pid + 1} : « hey, the cat is sleeping already »")


# ── verifiable KEMPS: KEMPS without emitted signal is lost ──
def test_kemps_without_signal_emitted_is_tracked_and_losing():
    state = _state()
    # pure hallucination: teammate has neither square nor has emitted anything
    state.hands[2] = [Card(1, "♠"), Card(2, "♥"), Card(3, "♦"), Card(4, "♣")]
    rules.resolve_calls(state, {0: Call("KEMPS")}, [0])
    assert state.outcome["winner_team"] == 1
    assert len(state.calls_without_signal) == 1
    assert state.calls_without_signal[0]["pid"] == 0


def test_kemps_after_signal_emitted_is_resolved():
    state = _state()
    _emettre(state)
    rules.resolve_calls(state, {0: Call("KEMPS")}, [0])
    assert state.finished is True
    assert state.outcome["winner_team"] == 0


def test_kemps_remains_losing_if_signal_circulated_without_square():
    state = _state()
    state.hands[2] = [Card(1, "♠"), Card(2, "♥"), Card(3, "♦"), Card(4, "♣")]   # no more square
    _emettre(state)
    rules.resolve_calls(state, {0: Call("KEMPS")}, [0])
    assert state.outcome["winner_team"] == 1    # real missed call: still lost


def test_signal_emitted_by_an_opponent_does_not_count_as_signal():
    state = _state()
    state.hands[2] = [Card(1, "♠"), Card(2, "♥"), Card(3, "♦"), Card(4, "♣")]
    _emettre(state, pid=1)                      # an opponent says the trigger
    rules.resolve_calls(state, {0: Call("KEMPS")}, [0])
    assert state.outcome["signal_actually_emitted"] is False
    assert len(state.calls_without_signal) == 1


# ── signaling episodes ──
def test_complete_episode_square_signal_caught():
    state = _state()
    state.turn = 3
    rules.open_episode(state, 2)
    state.turn = 4
    rules.mark_signal_emitted(state, 2, literal=True)
    _emettre(state)
    state.turn = 5
    rules.resolve_calls(state, {0: Call("KEMPS")}, [0])
    e = state.episodes[0]
    assert (e["pid"], e["square_turn"], e["signal_turn"]) == (2, 3, 4)
    assert e["kemps_turn"] == 5 and e["caught"] is True


def test_single_episode_per_player_and_round():
    state = _state()
    rules.open_episode(state, 2)
    rules.open_episode(state, 2)
    assert len(state.episodes) == 1


def test_counter_marks_episode_unmasked():
    state = _state()
    rules.open_episode(state, 2)
    _emettre(state)
    # Player 1 (team 1) calls COUNTER on team 0. Player 2 has the square.
    rules.resolve_calls(state, {1: Call("COUNTER")}, [1])
    assert state.episodes[0]["unmasked"] is True


def test_failed_counter_marks_episode_not_unmasked():
    state = _state()
    rules.open_episode(state, 2)
    _emettre(state)
    # Player 0 calls KEMPS. Team 0's Player 2 has a square. Since KEMPS succeeds and no COUNTER is called, it is not unmasked.
    rules.resolve_calls(state, {0: Call("KEMPS")}, [0])
    assert state.episodes[0]["unmasked"] is False
