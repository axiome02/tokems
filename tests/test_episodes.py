"""Volet 1 (KEMPS verifiable) et volet 3 (episodes de signalisation)."""
from kems.config import Config
from kems.engine import rules
from kems.engine.actions import Call
from kems.engine.cards import COULEURS, Card
from kems.orchestrator import setup


def _state():
    state = setup(Config(master_seed=1), ["bot"] * 4)
    rules.poser_signal(state, 0, "la phrase du chat", declencheur="le chat dort")
    rules.poser_signal(state, 1, "autre", declencheur="ventilateur")
    state.hands[2] = [Card(5, c) for c in COULEURS]      # le partenaire du joueur 0 a un carre
    return state


def _emettre(state, pid=2):
    """Le porteur du carre glisse son declencheur dans un message public."""
    rules._log(state, "MESSAGE", pid, f"Joueur {pid + 1} : « tiens, le chat dort deja »")


# ── volet 1 : un KEMPS sans signal emis est nul, pas perdant ──
def test_kemps_sans_signal_emis_est_trace_et_perdant():
    state = _state()
    # hallucination pure : le partenaire n'a NI carre NI emis quoi que ce soit
    state.hands[2] = [Card(1, "♠"), Card(2, "♥"), Card(3, "♦"), Card(4, "♣")]
    rules.resoudre_appels(state, {0: Call("KEMPS")}, [0])
    assert state.outcome["winner_team"] == 1
    assert len(state.appels_sans_signal) == 1
    assert state.appels_sans_signal[0]["pid"] == 0


def test_kemps_apres_signal_emis_est_resolu():
    state = _state()
    _emettre(state)
    rules.resoudre_appels(state, {0: Call("KEMPS")}, [0])
    assert state.finished is True
    assert state.outcome["winner_team"] == 0


def test_kemps_reste_perdant_si_le_signal_a_circule_sans_carre():
    state = _state()
    state.hands[2] = [Card(1, "♠"), Card(2, "♥"), Card(3, "♦"), Card(4, "♣")]   # plus de carre
    _emettre(state)
    rules.resoudre_appels(state, {0: Call("KEMPS")}, [0])
    assert state.outcome["winner_team"] == 1    # vrai appel rate : on perd toujours


def test_signal_emis_par_un_adversaire_ne_compte_pas_comme_signal():
    state = _state()
    state.hands[2] = [Card(1, "♠"), Card(2, "♥"), Card(3, "♦"), Card(4, "♣")]
    _emettre(state, pid=1)                      # un adversaire prononce le declencheur
    rules.resoudre_appels(state, {0: Call("KEMPS")}, [0])
    assert state.outcome["signal_reellement_emis"] is False
    assert len(state.appels_sans_signal) == 1


# ── volet 3 : l'episode de signalisation ──
def test_episode_complet_carre_signal_capte():
    state = _state()
    state.tour = 3
    rules.ouvrir_episode(state, 2)
    state.tour = 4
    rules.marquer_signal_emis(state, 2, litteral=True)
    _emettre(state)
    state.tour = 5
    rules.resoudre_appels(state, {0: Call("KEMPS")}, [0])
    e = state.episodes[0]
    assert (e["pid"], e["tour_carre"], e["tour_signal"]) == (2, 3, 4)
    assert e["tour_kemps"] == 5 and e["capte"] is True


def test_episode_unique_par_joueur_et_par_manche():
    state = _state()
    rules.ouvrir_episode(state, 2)
    rules.ouvrir_episode(state, 2)
    assert len(state.episodes) == 1


def test_riposte_marque_l_episode_demasque():
    state = _state()
    rules.poser_signal(state, 0, "la phrase du chat", declencheur="le chat dort")
    rules.ouvrir_episode(state, 2)
    _emettre(state)
    rules.resoudre_appels(state, {0: Call("KEMPS")}, [0])
    rules.resoudre_riposte(state, {1: "le chat dort", 3: "rien"})
    assert state.episodes[0]["demasque"] is True


def test_riposte_ratee_marque_l_episode_non_demasque():
    state = _state()
    rules.ouvrir_episode(state, 2)
    _emettre(state)
    rules.resoudre_appels(state, {0: Call("KEMPS")}, [0])
    rules.resoudre_riposte(state, {1: "la meteo", 3: "rien"})
    assert state.episodes[0]["demasque"] is False
