from kems.config import Config
from kems.engine import rules
from kems.engine.actions import Call, Take
from kems.engine.cards import SUITS, Card
from kems.orchestrator import setup


def test_kemps_success(armer_signal):
    cfg = Config(master_seed=1)
    state = setup(cfg, ["bot"] * 4)
    # teammate of player 0 = player 2 (team 0); force a square
    state.hands[2] = [Card(5, c) for c in SUITS]
    armer_signal(state, 0, 2)
    rules.resolve_calls(state, {0: Call("KEMPS")}, [0, 1, 2, 3])
    assert state.finished
    assert state.outcome["winner_team"] == 0
    assert state.outcome["success"] is True


def test_kemps_fail(armer_signal):
    cfg = Config(master_seed=1)
    state = setup(cfg, ["bot"] * 4)
    state.hands[2] = [Card(1, "♠"), Card(2, "♥"), Card(3, "♦"), Card(4, "♣")]
    armer_signal(state, 0, 2)
    rules.resolve_calls(state, {0: Call("KEMPS")}, [0, 1, 2, 3])
    assert state.outcome["winner_team"] == 1   # opposing team wins


def test_illegal_exchange_rejected():
    cfg = Config(master_seed=1)
    state = setup(cfg, ["bot"] * 4)
    non_existent_card = Take(from_center=Card(99, "♠"), discard=state.hands[0][0])
    assert rules.validate_and_apply_exchange(state, 0, non_existent_card) is False


def test_valid_exchange():
    cfg = Config(master_seed=1)
    state = setup(cfg, ["bot"] * 4)
    from_c = state.center[0]
    disc = state.hands[0][0]
    assert rules.validate_and_apply_exchange(state, 0, Take(from_c, disc)) is True
    assert from_c in state.hands[0]
    assert disc in state.center
