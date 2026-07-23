from kems.config import Config
from kems.engine import rules
from kems.engine.actions import Call, Take
from kems.engine.cards import COULEURS, Card
from kems.orchestrator import setup


def test_kemps_reussi(armer_signal):
    cfg = Config(master_seed=1)
    state = setup(cfg, ["bot"] * 4)
    # partenaire du joueur 0 = joueur 2 (equipe 0) ; on lui force un carre
    state.hands[2] = [Card(5, c) for c in COULEURS]
    armer_signal(state, 0, 2)
    rules.resoudre_appels(state, {0: Call("KEMPS")}, [0, 1, 2, 3])
    assert state.finished
    assert state.outcome["winner_team"] == 0
    assert state.outcome["success"] is True


def test_kemps_rate(armer_signal):
    cfg = Config(master_seed=1)
    state = setup(cfg, ["bot"] * 4)
    state.hands[2] = [Card(1, "♠"), Card(2, "♥"), Card(3, "♦"), Card(4, "♣")]
    armer_signal(state, 0, 2)
    rules.resoudre_appels(state, {0: Call("KEMPS")}, [0, 1, 2, 3])
    assert state.outcome["winner_team"] == 1   # l'equipe adverse gagne


def test_echange_illegal_rejete():
    cfg = Config(master_seed=1)
    state = setup(cfg, ["bot"] * 4)
    carte_inexistante = Take(from_center=Card(99, "♠"), discard=state.hands[0][0])
    assert rules.valider_et_appliquer_echange(state, 0, carte_inexistante) is False


def test_echange_valide():
    cfg = Config(master_seed=1)
    state = setup(cfg, ["bot"] * 4)
    from_c = state.center[0]
    disc = state.hands[0][0]
    assert rules.valider_et_appliquer_echange(state, 0, Take(from_c, disc)) is True
    assert from_c in state.hands[0]
    assert disc in state.center
