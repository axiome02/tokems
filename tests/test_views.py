import dataclasses

from kems.config import Config
from kems.engine import rules
from kems.engine.views import view_for
from kems.orchestrator import setup


def test_leakproofness():
    """A PlayerView must never contain anyone else's private info."""
    cfg = Config(master_seed=1, num_ranks=10)
    state = setup(cfg, ["bot"] * 4)

    rules.set_signal(state, 0, "banana")
    rules.set_signal(state, 1, "SECRET_MOUNTAIN")
    state.plans[1] = "SECRET_PLAN_OF_1"
    state.team_channels[1].append("PRIVATE_MESSAGE_TEAM_1")

    # player 0 is in team 0; team 1 is opposing
    v = view_for(state, 0)
    blob = str(dataclasses.asdict(v))

    assert v.my_signal == "banana"                  # I see MY signal
    assert "SECRET_MOUNTAIN" not in blob           # not the opponent's signal
    assert "SECRET_PLAN_OF_1" not in blob           # not anyone else's plan
    assert "PRIVATE_MESSAGE_TEAM_1" not in blob     # not the opposing private chat
    assert v.my_hand == state.hands[0]              # my hand = mine


def test_square_announced_by_referee():
    cfg = Config(master_seed=2, num_ranks=10)
    state = setup(cfg, ["bot"] * 4)
    from kems.engine.cards import SUITS, Card
    state.hands[0] = [Card(3, c) for c in SUITS]
    v = view_for(state, 0)
    assert v.has_square is True


def test_history_in_views():
    cfg = Config(master_seed=3, num_ranks=10)
    state = setup(cfg, ["bot"] * 4)
    
    state.scores[0] = 2
    state.scores[1] = 1
    state.round = 3
    state.round_history = [
        {"round": 1, "winner_team": 0, "reason": "KEMPS succeeded"},
        {"round": 2, "winner_team": 1, "reason": "COUNTER succeeded"}
    ]
    
    v = view_for(state, 0)
    assert v.scores == {0: 2, 1: 1}
    assert v.round == 3
    assert len(v.round_history) == 2
    
    # Test formatting in French
    from kems.llm.prompts_fr import _fmt_historique as _fmt_fr
    txt_fr = _fmt_fr(v)
    assert "SCORE DU MATCH : Ton equipe : 2 | Adversaires : 1" in txt_fr
    assert "MANCHE COURANTE : 3" in txt_fr
    assert "Manche 1 : Victoire (KEMPS succeeded)" in txt_fr
    assert "Manche 2 : Defaite (COUNTER succeeded)" in txt_fr

    # Test formatting in English
    from kems.llm.prompts_en import _fmt_historique as _fmt_en
    txt_en = _fmt_en(v)
    assert "MATCH SCORE: Your team: 2 | Opponents: 1" in txt_en
    assert "CURRENT ROUND: 3" in txt_en
    assert "Round 1: Win (KEMPS succeeded)" in txt_en
    assert "Round 2: Loss (COUNTER succeeded)" in txt_en
