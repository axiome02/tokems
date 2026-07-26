from kems.config import Config
from kems.engine.actions import Take, Pass
from kems.engine.cards import Card
from kems.orchestrator import exchange_phase, setup


class _ExchangeStub:
    def __init__(self, script):
        self.script = script
        self.i = 0

    def decide_card(self, view):
        action = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        return action


def test_exchange_phase_breaks_on_four_consecutive_passes():
    # 4 agents
    # Sub-turn 0:
    # Player 0: Pass (consecutive_passes = 1)
    # Player 1: Take (consecutive_passes = 0)
    # Player 2: Pass (consecutive_passes = 1)
    # Player 3: Pass (consecutive_passes = 2)
    # Sub-turn 1:
    # Player 0: Pass (consecutive_passes = 3)
    # Player 1: Pass (consecutive_passes = 4) -> BREAKS IMMEDIATELY! Player 2 and 3 do not play in Sub-turn 1!
    
    script_0 = [Pass(), Pass()]
    script_1 = [Take(Card(11, "♠"), Card(10, "♠")), Pass()] # takes JS, discards TS
    script_2 = [Pass(), Pass()]
    script_3 = [Pass(), Pass()]
    
    agents = {
        0: _ExchangeStub(script_0),
        1: _ExchangeStub(script_1),
        2: _ExchangeStub(script_2),
        3: _ExchangeStub(script_3),
    }
    
    cfg = Config(master_seed=1)
    state = setup(cfg, ["stub"] * 4)
    state.rng_order.shuffle = lambda lst: None
    
    # Set cards to make the swap valid
    state.hands[1] = [Card(7, "♠"), Card(8, "♠"), Card(9, "♠"), Card(10, "♠")]
    state.center = [Card(11, "♠"), Card(12, "♠"), Card(13, "♠"), Card(14, "♠")]
    
    exchange_phase(state, agents)
    
    # Assert that Player 1 played 2 times (one Take, one Pass)
    # Assert that Player 0 played 2 times (two Passes)
    # Assert that Player 2 played 1 time (one Pass in sub-turn 0, didn't play in sub-turn 1)
    # Assert that Player 3 played 1 time (one Pass in sub-turn 0, didn't play in sub-turn 1)
    assert agents[0].i == 2
    assert agents[1].i == 2
    assert agents[2].i == 1
    assert agents[3].i == 1
    
    # Assert that the center was updated and swept (Player 1 has JS, TS was swept to discard)
    assert Card(10, "♠") in state.discard
    assert Card(11, "♠") not in state.discard
    assert Card(11, "♠") in state.hands[1]
