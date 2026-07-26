import json

from kems import batch
from kems.batch import (NEVER_SPOKE, SPOKE_WITHOUT_RECOGNITION, RECOGNIZED,
                        agreger, episode_state, extraire_partie, extraire_tout)
from kems.config import Config
from kems.engine import rules
from kems.engine.actions import Call
from kems.engine.cards import SUITS, Card
from kems.orchestrator import setup


def _state(**cfg):
    return setup(Config(master_seed=1, **cfg), ["bot"] * 4)


# --- classification of the 3 states -----------------------------

def test_state_recognized_on_literal_signal():
    assert episode_state({"speech_turn": 3, "signal_turn": 3}) == RECOGNIZED


def test_state_spoke_without_recognition_on_paraphrase():
    # spoke (speech_turn) but engine didn't catch trigger (signal_turn is None)
    assert episode_state({"speech_turn": 3, "signal_turn": None}) == SPOKE_WITHOUT_RECOGNITION


def test_state_never_spoke_on_silence():
    assert episode_state({"speech_turn": None, "signal_turn": None}) == NEVER_SPOKE


# --- extraction from GameState -------------------------------------------------

def _win_by_kemps(state, team):
    caller = state.team_players(team)[0]
    partner = state.partner(caller)
    state.hands[partner] = [Card(5, c) for c in SUITS]
    rules.set_signal(state, team, "convention", trigger="the cat is sleeping")
    rules.open_episode(state, partner)
    rules._log(state, "MESSAGE", partner, "« hey, the cat is sleeping already »")
    rules.mark_signal_emitted(state, partner, literal=True)
    rules.resolve_calls(state, {caller: Call("KEMPS")}, [caller])
    state.comeback_team = None
    rules.close_round(state)


def test_extraire_partie_reads_score_and_winner():
    state = _state(points_to_win=1)
    _win_by_kemps(state, 0)
    p = extraire_partie(state, {"grand_total": 1234}, seed=1)
    assert p["seed"] == 1
    assert p["vainqueur"] == 0
    assert p["score_0"] == 1 and p["score_1"] == 0
    assert p["tokens_total"] == 1234
    assert p["nb_episodes"] == 1


def test_extraire_tout_produces_episodes_and_codes():
    state = _state(points_to_win=1)
    _win_by_kemps(state, 0)
    dump = extraire_tout(state, {"grand_total": 10}, seed=7)
    assert dump["seed"] == 7
    assert len(dump["episodes"]) == 1
    assert dump["episodes"][0]["etat"] == RECOGNIZED
    assert dump["episodes"][0]["capte"] is True
    # signal invented is correctly retrieved
    assert any(c["signal"] == "convention" for c in dump["codes"])


# --- aggregation: 3 states and transmission bounds ------------------------------

def test_agreger_keeps_all_three_states():
    dumps = [{
        "partie": {"tokens_total": 0, "nb_ripostes": 0, "ripostes_reussies": 0,
                   "appels_sans_signal": 0, "emissions_sans_carre": 0},
        "episodes": [
            {"etat": RECOGNIZED, "modele": "m"},
            {"etat": SPOKE_WITHOUT_RECOGNITION, "modele": "m"},
            {"etat": NEVER_SPOKE, "modele": "m"},
            {"etat": NEVER_SPOKE, "modele": "m"},
        ],
    }]
    r = agreger(dumps)
    assert r["etats_episodes"] == {RECOGNIZED: 1, SPOKE_WITHOUT_RECOGNITION: 1, NEVER_SPOKE: 2}
    assert r["transmission_minorant"] == 0.25
    assert r["transmission_borne_haute"] == 0.5


def test_agreger_opponent_detection_rate_from_ripostes():
    dumps = [{
        "partie": {"tokens_total": 0, "nb_ripostes": 2, "ripostes_reussies": 1,
                   "appels_sans_signal": 0, "emissions_sans_carre": 0},
        "episodes": [],
    }]
    r = agreger(dumps)
    assert r["detection_adverse"] == 0.5


def test_agreger_on_zero_episodes_does_not_divide_by_zero():
    r = agreger([])
    assert r["nb_parties"] == 0
    assert r["transmission_minorant"] is None
    assert r["detection_adverse"] is None


# --- crash-safe write / regeneration --------------------------------------------------

def test_regenerer_writes_csv_and_summary(tmp_path):
    games = tmp_path / "games"
    games.mkdir()
    dump = {
        "seed": 3, "interrompu": False,
        "partie": {"seed": 3, "tokens_total": 5, "nb_ripostes": 0, "ripostes_reussies": 0,
                   "appels_sans_signal": 0, "emissions_sans_carre": 0, "nb_episodes": 1},
        "episodes": [{"seed": 3, "etat": RECOGNIZED, "modele": "mistral", "capte": True}],
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
