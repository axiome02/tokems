import dataclasses

from kems.config import Config
from kems.engine import rules
from kems.engine.views import vue_pour
from kems.orchestrator import setup


def test_etancheite():
    """Une PlayerView ne doit jamais contenir l'info privee d'autrui."""
    cfg = Config(master_seed=1, nb_rangs=10)
    state = setup(cfg, ["bot"] * 4)

    rules.poser_signal(state, 0, "banane")
    rules.poser_signal(state, 1, "MONTAGNE_SECRETE")
    state.plans[1] = "PLAN_SECRET_DE_1"
    state.team_channels[1].append("MESSAGE_PRIVE_EQUIPE_1")

    # joueur 0 est dans l'equipe 0 ; l'equipe 1 est adverse
    v = vue_pour(state, 0)
    blob = str(dataclasses.asdict(v))

    assert v.mon_signal == "banane"                 # je vois MON signal
    assert "MONTAGNE_SECRETE" not in blob           # pas le signal adverse
    assert "PLAN_SECRET_DE_1" not in blob           # pas le plan d'autrui
    assert "MESSAGE_PRIVE_EQUIPE_1" not in blob      # pas le chat prive adverse
    assert v.ma_main == state.hands[0]              # ma main = la mienne


def test_carre_annonce_par_arbitre():
    cfg = Config(master_seed=2, nb_rangs=10)
    state = setup(cfg, ["bot"] * 4)
    from kems.engine.cards import COULEURS, Card
    state.hands[0] = [Card(3, c) for c in COULEURS]
    v = vue_pour(state, 0)
    assert v.jai_un_carre is True
