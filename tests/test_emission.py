"""Les deux regles arbitrees par le moteur autour du declencheur :
   1. on n'emet pas son code sans carre ;
   2. un adversaire qui prononce le code par hasard ne signale rien.
"""
from kems.config import Config
from kems.engine import rules
from kems.engine.cards import COULEURS, Card
from kems.orchestrator import setup


def _state():
    state = setup(Config(master_seed=1), ["bot"] * 4)
    # equipe 0 = joueurs 0 et 2 ; equipe 1 = joueurs 1 et 3
    rules.poser_signal(state, 0, "on glisse la phrase sur le chat qui dort",
                       declencheur="le chat dort sur le canape")
    rules.poser_signal(state, 1, "autre chose", declencheur="ventilateur")
    return state


def test_declencheur_par_defaut_sur_la_convention():
    state = setup(Config(master_seed=1), ["bot"] * 4)
    rules.poser_signal(state, 0, "ananas")           # pas de declencheur explicite
    assert state.declencheurs[0] == "ananas"


# ── regle 1 : emettre son code sans carre est un coup illegal ──
def test_emission_sans_carre_est_interdite():
    state = _state()
    assert rules.emission_sans_carre(state, 0, "tiens, le chat dort sur le canape ce soir") is True


def test_emission_autorisee_avec_un_carre():
    state = _state()
    state.hands[0] = [Card(5, c) for c in COULEURS]
    assert rules.emission_sans_carre(state, 0, "tiens, le chat dort sur le canape ce soir") is False


def test_message_ordinaire_jamais_bloque():
    state = _state()
    assert rules.emission_sans_carre(state, 0, "belle partie, vous jouez bien") is False


def test_emission_jugee_sur_le_code_de_SA_propre_equipe():
    state = _state()
    # le joueur 0 (equipe 0) parle du ventilateur : c'est le code ADVERSE, pas le sien
    assert rules.emission_sans_carre(state, 0, "ce ventilateur fait un bruit fou") is False


# ── regle 2 : un adversaire qui tombe sur le code, c'est du hasard ──
def test_code_prononce_par_le_partenaire_compte():
    state = _state()
    rules._log(state, "MESSAGE", 2, "Joueur 3 : « le chat dort sur le canape, quelle paix »")
    assert rules.signal_emis_par_le_partenaire(state, 0) is True


def test_code_prononce_par_un_adversaire_ne_compte_pas():
    state = _state()
    rules._log(state, "MESSAGE", 1, "Joueur 2 : « le chat dort sur le canape, quelle paix »")
    assert rules.signal_emis_par_le_partenaire(state, 0) is False


def test_aucun_message_aucun_signal():
    state = _state()
    assert rules.signal_emis_par_le_partenaire(state, 0) is False
