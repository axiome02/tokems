"""The two rules arbitrated by the engine around the trigger:
   1. you do not emit your code without a square;
   2. an opponent pronouncing the code by accident does not signal anything.
"""
from kems.config import Config
from kems.engine import rules
from kems.engine.cards import SUITS, Card
from kems.orchestrator import setup


def _state():
    state = setup(Config(master_seed=1), ["bot"] * 4)
    # team 0 = players 0 and 2; team 1 = players 1 and 3
    rules.set_signal(state, 0, "we slip the phrase about the sleeping cat",
                       trigger="the cat is sleeping on the couch")
    rules.set_signal(state, 1, "something else", trigger="fan")
    return state


def test_default_trigger_on_convention():
    state = setup(Config(master_seed=1), ["bot"] * 4)
    rules.set_signal(state, 0, "pineapple")           # no explicit trigger
    assert state.triggers[0] == "pineapple"


# ── rule 1: emitting code without a square is detected as an unauthorized emission ──
def test_emission_without_square_is_flagged():
    state = _state()
    assert rules.emission_without_square(state, 0, "hey, the cat is sleeping on the couch tonight") is True


def test_emission_allowed_with_a_square():
    state = _state()
    state.hands[0] = [Card(5, c) for c in SUITS]
    assert rules.emission_without_square(state, 0, "hey, the cat is sleeping on the couch tonight") is False


def test_ordinary_message_never_flagged():
    state = _state()
    assert rules.emission_without_square(state, 0, "nice game, you play well") is False


def test_emission_judged_on_its_own_team_code():
    state = _state()
    # player 0 (team 0) talks about the fan: this is the OPPONENT'S code, not theirs
    assert rules.emission_without_square(state, 0, "this fan makes a crazy noise") is False


# ── rule 2: an opponent happening to say the code is just coincidence ──
def test_code_pronounced_by_partner_counts():
    state = _state()
    rules._log(state, "MESSAGE", 2, "Player 3: « the cat is sleeping on the couch, so peaceful »")
    assert rules.signal_emitted_by_partner(state, 0) is True


def test_code_pronounced_by_opponent_does_not_count():
    state = _state()
    rules._log(state, "MESSAGE", 1, "Player 2: « the cat is sleeping on the couch, so peaceful »")
    assert rules.signal_emitted_by_partner(state, 0) is False


def test_no_messages_no_signal():
    state = _state()
    assert rules.signal_emitted_by_partner(state, 0) is False
