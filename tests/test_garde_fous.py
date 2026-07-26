"""Tests for safeguard features and logic bugs."""
from kems.config import Config
from kems.engine import rules
from kems.engine.actions import Call
from kems.engine.cards import SUITS, Card
from kems.orchestrator import new_round, setup


def _state(**cfg):
    state = setup(Config(master_seed=1, **cfg), ["bot"] * 4)
    rules.set_signal(state, 0, "a misspelled word", trigger="kare")
    rules.set_signal(state, 1, "other", trigger="fan")
    return state


# ── safeguard 1: never punish a successful but paraphrased transmission ──
def test_kemps_valid_if_partner_has_square_even_without_literal_trigger():
    """Real case: convention "a misspelled word", emitted "karre" instead of "kare"."""
    state = _state()
    state.hands[2] = [Card(5, c) for c in SUITS]
    rules._log(state, "MESSAGE", 2, "Player 3: « the word karre floats in the air »")
    rules.resolve_calls(state, {0: Call("KEMPS")}, [0])
    assert state.outcome["winner_team"] == 0


# ── blind call loses the round ──
def test_blind_kemps_loses_round():
    state = _state()
    rules.resolve_calls(state, {0: Call("KEMPS")}, [0])
    assert state.finished is True
    assert state.outcome["winner_team"] == 1
    assert len(state.calls_without_signal) == 1
    assert state.calls_without_signal[0]["winner"] is False


def test_blind_kemps_wins_if_partner_had_square():
    """Lucky guess counts as win, but it is logged."""
    state = _state()
    state.hands[2] = [Card(5, c) for c in SUITS]
    rules.resolve_calls(state, {0: Call("KEMPS")}, [0])
    assert state.outcome["winner_team"] == 0
    assert state.calls_without_signal[0]["winner"] is True


def test_emitting_own_code_without_square_is_legal():
    """Bluffing with own signal is allowed: we measure it, we don't block it."""
    state = _state()
    assert rules.emission_without_square(state, 0, "the word kare hangs here") is True


# ── safeguard 2: public chat is not cleared, round must be filtered ──
def test_signal_from_previous_round_no_longer_valid():
    state = _state()
    rules._log(state, "MESSAGE", 2, "Player 3: « here is kare »")
    assert rules.signal_emitted_by_partner(state, 0) is True
    new_round(state)
    assert rules.signal_emitted_by_partner(state, 0) is False


# ── safeguard 3: do not censor on a very common trigger ──
def test_short_trigger_not_exploitable():
    assert rules.trigger_exploitable("42") is False
    assert rules.trigger_exploitable("—") is False
    assert rules.trigger_exploitable("kare") is True
    assert rules.trigger_exploitable("☀️") is True      # short but unambiguous


def test_innocent_message_not_censored_on_weak_trigger():
    state = _state()
    rules.set_signal(state, 0, "convention", trigger="42")
    assert rules.emission_without_square(state, 0, "I saw a 42 pass by, hey") is False


# ── safeguard 4: metric must not say 'never emitted' when paraphrased ──
def test_episode_distinguishes_paraphrase_and_silence():
    state = _state()
    state.hands[0] = [Card(5, c) for c in SUITS]
    state.turn = 2
    rules.open_episode(state, 0)
    state.turn = 3
    rules.mark_signal_emitted(state, 0, literal=False)
    e = state.episodes[0]
    assert e["speech_turn"] == 3 and e["signal_turn"] is None
    state.turn = 4
    rules.mark_signal_emitted(state, 0, literal=True)
    assert e["signal_turn"] == 4 and e["speech_turn"] == 3
