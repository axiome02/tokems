from kems.config import Config
from kems.engine import rules
from kems.engine.actions import Call
from kems.engine.cards import COULEURS, Card
from kems.orchestrator import nouvelle_manche, setup


def _state(**cfg):
    return setup(Config(master_seed=1, **cfg), ["bot"] * 4)


def _gagner_manche(state, equipe):
    """L'equipe donnee remporte la manche courante via un KEMPS reussi."""
    appelant = state.joueurs_equipe(equipe)[0]
    porteur = state.partenaire(appelant)
    state.hands[porteur] = [Card(5, c) for c in COULEURS]
    rules.poser_signal(state, equipe, "convention", declencheur="le chat dort")
    rules._log(state, "MESSAGE", porteur, "« tiens, le chat dort deja »")   # arme l'appel
    rules.resoudre_appels(state, {appelant: Call("KEMPS")}, [appelant])
    state.riposte_equipe = None          # on ignore la riposte ici
    rules.cloturer_manche(state)


def test_point_attribue_et_match_non_termine():
    state = _state()
    _gagner_manche(state, 0)
    assert state.scores == {0: 1, 1: 0}
    assert state.match_termine is False
    assert len(state.historique_manches) == 1


def test_match_gagne_a_trois_points():
    state = _state()
    for _ in range(3):
        if state.match_termine:
            break
        _gagner_manche(state, 0)
        if not state.match_termine:
            nouvelle_manche(state)
    assert state.scores[0] == 3
    assert state.match_termine is True
    assert state.vainqueur_match == 0


def test_manche_nulle_ne_donne_aucun_point():
    state = _state(max_tours=1)
    state.tour_manche = 1
    rules.verifier_fin(state)
    rules.cloturer_manche(state)
    assert state.scores == {0: 0, 1: 0}
    assert state.match_termine is False


def test_max_manches_arrete_le_match_au_score():
    state = _state(max_manches=2)
    _gagner_manche(state, 0)
    nouvelle_manche(state)
    _gagner_manche(state, 1)
    assert state.match_termine is True
    assert state.vainqueur_match is None      # 1-1 -> nul
    assert state.scores == {0: 1, 1: 1}


def test_nouvelle_manche_redistribue_sans_effacer_le_chat():
    state = _state()
    _gagner_manche(state, 0)
    mains_avant = {p: list(h) for p, h in state.hands.items()}
    lignes_avant = len(state.public_log)
    nouvelle_manche(state)
    assert state.manche == 2
    # la nouvelle donne appartient deja au 1er tour de la manche (sinon « Tour fantome »)
    assert state.tour_manche == 1 and state.centres_joues == 0
    assert state.finished is False and state.outcome is None
    assert state.hands != mains_avant
    assert all(len(h) == 4 for h in state.hands.values())
    assert len(state.public_log) > lignes_avant      # le chat public ne s'efface jamais


def test_signal_brule_seulement_apres_une_riposte_reussie():
    state = _state()
    rules.poser_signal(state, 0, "☀️")
    state.hands[2] = [Card(5, c) for c in COULEURS]
    rules._log(state, "MESSAGE", 2, "Joueur 3 : « belle soiree ☀️ »")   # arme l'appel
    rules.resoudre_appels(state, {0: Call("KEMPS")}, [0])
    rules.resoudre_riposte(state, {1: "l'emoji ☀️", 3: "rien"})
    rules.cloturer_manche(state)
    assert rules.signal_brule(state, 0) is True      # l'equipe 0 s'est fait demasquer
    assert rules.signal_brule(state, 1) is False
    assert state.scores == {0: 0, 1: 1}              # la riposte a renverse le point


def test_signal_non_brule_si_la_riposte_echoue():
    state = _state()
    rules.poser_signal(state, 0, "☀️")
    state.hands[2] = [Card(5, c) for c in COULEURS]
    rules._log(state, "MESSAGE", 2, "Joueur 3 : « belle soiree ☀️ »")   # arme l'appel
    rules.resoudre_appels(state, {0: Call("KEMPS")}, [0])
    rules.resoudre_riposte(state, {1: "la meteo", 3: "rien"})
    rules.cloturer_manche(state)
    assert rules.signal_brule(state, 0) is False
    assert state.scores == {0: 1, 1: 0}


def test_riposte_ratee_ne_revele_pas_le_signal_dans_le_chat_public():
    state = _state()
    rules.poser_signal(state, 0, "ananas")
    state.hands[2] = [Card(5, c) for c in COULEURS]
    rules.resoudre_appels(state, {0: Call("KEMPS")}, [0])
    rules.resoudre_riposte(state, {1: "banane", 3: "cerise"})
    # le match continue : le vrai signal ne doit apparaitre nulle part dans le chat
    assert not any("ananas" in ev.texte for ev in state.public_log)


def test_manche_nulle_n_enchaine_pas_si_max_manches_vaut_1():
    # piege observe : --points 1 n'empeche pas l'enchainement, car une nulle ne donne aucun point
    state = _state(max_tours=6, max_manches=1, points_pour_gagner=1)
    state.tour_manche = 6
    rules.verifier_fin(state)
    rules.cloturer_manche(state)
    assert state.match_termine is True
    assert state.vainqueur_match is None


def test_la_nouvelle_donne_porte_le_numero_du_tour_qui_commence():
    """Bug « Tour fantome » : la manche 2 s'ouvrait sur le dernier tour de la manche 1."""
    state = _state()
    state.tour = 4
    _gagner_manche(state, 0)
    nouvelle_manche(state)
    donne = state.public_log[-1]  # nouvelle_manche() ne logge que cet unique evenement
    assert donne.tour == 5 and donne.manche == 2
