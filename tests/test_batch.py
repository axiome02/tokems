import json

from kems import batch
from kems.batch import (JAMAIS_PARLE, PARLE_SANS_RECONNAISSANCE, RECONNU,
                        agreger, etat_episode, extraire_partie, extraire_tout)
from kems.config import Config
from kems.engine import rules
from kems.engine.actions import Call
from kems.engine.cards import COULEURS, Card
from kems.orchestrator import setup


def _state(**cfg):
    return setup(Config(master_seed=1, **cfg), ["bot"] * 4)


# --- classification des 3 etats : le point le plus important -----------------------------

def test_etat_reconnu_quand_signal_litteral():
    assert etat_episode({"tour_parole": 3, "tour_signal": 3}) == RECONNU


def test_etat_parle_sans_reconnaissance_quand_paraphrase():
    # a parle (tour_parole) mais le moteur n'a pas reconnu le declencheur (tour_signal None)
    assert etat_episode({"tour_parole": 3, "tour_signal": None}) == PARLE_SANS_RECONNAISSANCE


def test_etat_jamais_parle_quand_muet():
    assert etat_episode({"tour_parole": None, "tour_signal": None}) == JAMAIS_PARLE


# --- extraction depuis un vrai GameState -------------------------------------------------

def _gagner_par_kemps(state, equipe):
    appelant = state.joueurs_equipe(equipe)[0]
    porteur = state.partenaire(appelant)
    state.hands[porteur] = [Card(5, c) for c in COULEURS]
    rules.poser_signal(state, equipe, "convention", declencheur="le chat dort")
    rules.ouvrir_episode(state, porteur)
    rules._log(state, "MESSAGE", porteur, "« tiens, le chat dort deja »")
    rules.marquer_signal_emis(state, porteur, litteral=True)
    rules.resoudre_appels(state, {appelant: Call("KEMPS")}, [appelant])
    state.riposte_equipe = None
    rules.cloturer_manche(state)


def test_extraire_partie_lit_le_score_et_le_vainqueur():
    state = _state(points_pour_gagner=1)
    _gagner_par_kemps(state, 0)
    p = extraire_partie(state, {"grand_total": 1234}, seed=1)
    assert p["seed"] == 1
    assert p["vainqueur"] == 0
    assert p["score_0"] == 1 and p["score_1"] == 0
    assert p["tokens_total"] == 1234
    assert p["nb_episodes"] == 1


def test_extraire_tout_produit_episodes_et_codes():
    state = _state(points_pour_gagner=1)
    _gagner_par_kemps(state, 0)
    dump = extraire_tout(state, {"grand_total": 10}, seed=7)
    assert dump["seed"] == 7
    assert len(dump["episodes"]) == 1
    assert dump["episodes"][0]["etat"] == RECONNU
    assert dump["episodes"][0]["capte"] is True
    # le signal invente est bien remonte pour la galerie
    assert any(c["signal"] == "convention" for c in dump["codes"])


# --- agregation : les 3 etats et les bornes de transmission ------------------------------

def test_agreger_remonte_les_trois_etats_sans_les_ecraser():
    dumps = [{
        "partie": {"tokens_total": 0, "nb_ripostes": 0, "ripostes_reussies": 0,
                   "appels_sans_signal": 0, "emissions_sans_carre": 0},
        "episodes": [
            {"etat": RECONNU, "modele": "m"},
            {"etat": PARLE_SANS_RECONNAISSANCE, "modele": "m"},
            {"etat": JAMAIS_PARLE, "modele": "m"},
            {"etat": JAMAIS_PARLE, "modele": "m"},
        ],
    }]
    r = agreger(dumps)
    assert r["etats_episodes"] == {RECONNU: 1, PARLE_SANS_RECONNAISSANCE: 1, JAMAIS_PARLE: 2}
    # minorant = reconnu seul ; borne haute inclut « a parle sans reconnaissance »
    assert r["transmission_minorant"] == 0.25
    assert r["transmission_borne_haute"] == 0.5


def test_agreger_detection_adverse_depuis_les_ripostes():
    dumps = [{
        "partie": {"tokens_total": 0, "nb_ripostes": 2, "ripostes_reussies": 1,
                   "appels_sans_signal": 0, "emissions_sans_carre": 0},
        "episodes": [],
    }]
    r = agreger(dumps)
    assert r["detection_adverse"] == 0.5


def test_agreger_sur_zero_episode_ne_divise_pas_par_zero():
    r = agreger([])
    assert r["nb_parties"] == 0
    assert r["transmission_minorant"] is None
    assert r["detection_adverse"] is None


# --- ecriture / regeneration crash-safe --------------------------------------------------

def test_regenerer_ecrit_les_csv_et_le_summary(tmp_path):
    games = tmp_path / "games"
    games.mkdir()
    dump = {
        "seed": 3, "interrompu": False,
        "partie": {"seed": 3, "tokens_total": 5, "nb_ripostes": 0, "ripostes_reussies": 0,
                   "appels_sans_signal": 0, "emissions_sans_carre": 0, "nb_episodes": 1},
        "episodes": [{"seed": 3, "etat": RECONNU, "modele": "mistral", "capte": True}],
        "codes": [{"seed": 3, "equipe": 0, "modele": "mistral", "signal": "kezako",
                   "declencheur": "kezako"}],
    }
    (games / "3.json").write_text(json.dumps(dump), encoding="utf-8")

    resume = batch.regenerer(str(tmp_path))

    assert (tmp_path / "parties.csv").exists()
    assert (tmp_path / "episodes.csv").exists()
    assert (tmp_path / "codes.csv").exists()
    saved = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert saved["nb_parties"] == 1
    assert resume["transmission_minorant"] == 1.0
