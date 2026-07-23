from kems.config import Config
from kems.engine import rules
from kems.engine.actions import Call
from kems.engine.cards import COULEURS, Card
from kems.engine.signaux import normaliser, signal_trouve
from kems.llm.parse import parse_riposte
from kems.orchestrator import setup


def _partie_avec_kemps_reussi():
    """Equipe 0 gagne sur un KEMPS reussi -> l'equipe 1 riposte en visant le signal « ☀️ »."""
    state = setup(Config(master_seed=1), ["bot"] * 4)
    state.hands[2] = [Card(5, c) for c in COULEURS]      # carre chez le partenaire du joueur 0
    rules.poser_signal(state, 0, "☀️")                   # le signal a demasquer
    rules.poser_signal(state, 1, "le mot tranquille")
    rules._log(state, "MESSAGE", 2, "Joueur 3 : « belle soiree ☀️ »")   # arme l'appel
    rules.resoudre_appels(state, {0: Call("KEMPS")}, [0, 1, 2, 3])
    return state


# ───────────────────────── arbitrage du signal (deterministe) ─────────────────────
def test_normalisation_ignore_accents_casse_ponctuation():
    assert normaliser("  Le MOT « Tranquillé » ! ") == "le mot tranquille"


def test_signal_cite_dans_une_phrase():
    assert signal_trouve("☀️", "ils utilisent l'emoji soleil ☀️")
    assert signal_trouve("tranquille", "je crois que le mot est 'tranquille'")


def test_reponse_nue_pour_un_signal_verbeux():
    assert signal_trouve("le mot 'tranquille'", "tranquille")


def test_selecteur_de_variante_ignore():
    assert signal_trouve("☀️", "☀")


def test_reponse_a_cote():
    assert not signal_trouve("☀️", "un mot sur la meteo")
    assert not signal_trouve("tranquille", "calme")


def test_reponse_vide_ou_absente_ne_gagne_jamais():
    assert not signal_trouve("☀️", "")
    assert not signal_trouve("", "☀️")
    assert not signal_trouve("<aucun>", "aucun")


def test_reponse_trop_courte_non_acceptee():
    # 'le' est inclus dans le signal mais ne demontre aucune deduction
    assert not signal_trouve("le mot tranquille", "le")


# ───────────────────────────── ouverture de la riposte ────────────────────────────
def test_kemps_reussi_ouvre_la_riposte_du_perdant():
    state = _partie_avec_kemps_reussi()
    assert state.finished
    assert state.outcome["winner_team"] == 0
    assert state.riposte_equipe == 1


def test_kemps_rate_n_ouvre_pas_de_riposte():
    state = setup(Config(master_seed=1), ["bot"] * 4)
    state.hands[2] = [Card(1, "♠"), Card(2, "♥"), Card(3, "♦"), Card(4, "♣")]
    rules.poser_signal(state, 0, "☀️")
    rules._log(state, "MESSAGE", 2, "Joueur 3 : « belle soiree ☀️ »")
    rules.resoudre_appels(state, {0: Call("KEMPS")}, [0, 1, 2, 3])
    assert state.riposte_equipe is None


def test_counter_n_ouvre_pas_de_riposte():
    state = setup(Config(master_seed=1), ["bot"] * 4)
    state.hands[1] = [Card(5, c) for c in COULEURS]
    rules.resoudre_appels(state, {0: Call("COUNTER")}, [0, 1, 2, 3])
    assert state.outcome["winner_team"] == 0
    assert state.riposte_equipe is None


# ─────────────────────────── resolution de la riposte ─────────────────────────────
def test_riposte_reussie_renverse_la_partie():
    state = _partie_avec_kemps_reussi()
    rules.resoudre_riposte(state, {1: "aucune idee", 3: "ils glissent l'emoji ☀️"})
    assert state.outcome["winner_team"] == 1
    assert state.outcome["riposte"]["reussie"] is True
    assert state.players[3].nom in state.outcome["reason"]  # nomme qui a demasque le signal


def test_riposte_manquee_laisse_le_vainqueur_initial():
    state = _partie_avec_kemps_reussi()
    rules.resoudre_riposte(state, {1: "le mot bonjour", 3: "un truc sur la meteo"})
    assert state.outcome["winner_team"] == 0
    assert state.outcome["riposte"]["reussie"] is False
    assert len(state.outcome["riposte"]["tentatives"]) == 2


def test_riposte_consommee_une_seule_fois():
    state = _partie_avec_kemps_reussi()
    rules.resoudre_riposte(state, {1: "", 3: ""})
    assert state.riposte_equipe is None
    rules.resoudre_riposte(state, {1: "☀️", 3: "☀️"})   # sans effet
    assert state.outcome["winner_team"] == 0


# ──────────────────────────────── parsing ─────────────────────────────────────────
def test_parse_riposte_ligne_structuree():
    txt = "RAISONNEMENT: le soleil revient trop souvent\nSIGNAL_ADVERSE: **☀️**"
    assert parse_riposte(txt).reponse == "☀️"


def test_parse_riposte_repli_derniere_ligne():
    assert parse_riposte("je pense que c'est\nl'emoji soleil").reponse == "l'emoji soleil"
