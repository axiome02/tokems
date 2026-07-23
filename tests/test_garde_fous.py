"""Les quatre bugs trouves a la revue de bout en bout (partie 909)."""
from kems.config import Config
from kems.engine import rules
from kems.engine.actions import Call
from kems.engine.cards import COULEURS, Card
from kems.orchestrator import nouvelle_manche, setup


def _state(**cfg):
    state = setup(Config(master_seed=1, **cfg), ["bot"] * 4)
    rules.poser_signal(state, 0, "un mot mal orthographie", declencheur="kare")
    rules.poser_signal(state, 1, "autre", declencheur="ventilateur")
    return state


# ── bug 1 : ne jamais punir une transmission reussie mais paraphrasee ──
def test_kemps_valide_si_le_partenaire_a_un_carre_meme_sans_declencheur_litteral():
    """Cas reel : convention « un mot mal orthographie », emis « karre » au lieu de « kare »."""
    state = _state()
    state.hands[2] = [Card(5, c) for c in COULEURS]
    rules._log(state, "MESSAGE", 2, "Joueur 3 : « le mot karre flotte dans l'air »")
    rules.resoudre_appels(state, {0: Call("KEMPS")}, [0])
    assert state.outcome["winner_team"] == 0


# ── le moteur n'annule plus rien : un appel est un pari, et le pari se paie ──
def test_kemps_a_l_aveugle_fait_perdre_la_manche():
    state = _state()
    rules.resoudre_appels(state, {0: Call("KEMPS")}, [0])
    assert state.finished is True
    assert state.outcome["winner_team"] == 1
    assert len(state.appels_sans_signal) == 1
    assert state.appels_sans_signal[0]["gagnant"] is False


def test_kemps_a_l_aveugle_gagne_si_le_partenaire_avait_un_carre():
    """Le moteur ne protege personne : un coup de chance reste un coup gagnant, mais il est trace."""
    state = _state()
    state.hands[2] = [Card(5, c) for c in COULEURS]
    rules.resoudre_appels(state, {0: Call("KEMPS")}, [0])
    assert state.outcome["winner_team"] == 0
    assert state.appels_sans_signal[0]["gagnant"] is True


def test_emettre_son_code_sans_carre_est_legal():
    """Bluffer avec son propre signal est un coup autorise : on mesure, on ne censure pas."""
    state = _state()
    assert rules.emission_sans_carre(state, 0, "le mot kare traine ici") is True


# ── bug 2 : le chat public n'est pas efface, il faut filtrer la manche ──
def test_signal_d_une_manche_precedente_ne_vaut_plus():
    state = _state()
    rules._log(state, "MESSAGE", 2, "Joueur 3 : « voici kare »")
    assert rules.signal_emis_par_le_partenaire(state, 0) is True
    nouvelle_manche(state)
    assert rules.signal_emis_par_le_partenaire(state, 0) is False


# ── bug 3 : ne pas censurer sur un declencheur trop courant ──
def test_declencheur_trop_court_n_est_pas_exploitable():
    assert rules.declencheur_exploitable("42") is False
    assert rules.declencheur_exploitable("—") is False
    assert rules.declencheur_exploitable("kare") is True
    assert rules.declencheur_exploitable("☀️") is True      # court mais non ambigu


def test_message_innocent_non_censure_sur_declencheur_faible():
    state = _state()
    rules.poser_signal(state, 0, "convention", declencheur="42")
    assert rules.emission_sans_carre(state, 0, "j'ai vu passer un 42, tiens") is False


# ── bug 4 : la metrique ne doit pas dire « jamais emis » quand il a paraphrase ──
def test_episode_distingue_paraphrase_et_silence():
    state = _state()
    state.hands[0] = [Card(5, c) for c in COULEURS]
    state.tour = 2
    rules.ouvrir_episode(state, 0)
    state.tour = 3
    rules.marquer_signal_emis(state, 0, litteral=False)
    e = state.episodes[0]
    assert e["tour_parole"] == 3 and e["tour_signal"] is None
    state.tour = 4
    rules.marquer_signal_emis(state, 0, litteral=True)
    assert e["tour_signal"] == 4 and e["tour_parole"] == 3
