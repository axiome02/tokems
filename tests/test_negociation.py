from kems.config import Config
from kems.engine.actions import Nego
from kems.llm.parse import parse_negociation
from kems.orchestrator import negotiation, setup


class _Stub:
    """Agent de negociation scripte : (msg, proposition, accord) ou (msg, proposition, accord,
    declencheur) appel par appel. A defaut de declencheur explicite : declencheur = proposition
    (comme le prompt le demande : le texte exact a reperer)."""

    def __init__(self, scripted):
        self._scripted = scripted
        self._i = 0

    def negotiate(self, view):
        item = self._scripted[min(self._i, len(self._scripted) - 1)]
        msg, prop, accord = item[0], item[1], item[2]
        decl = item[3] if len(item) > 3 else prop
        self._i += 1
        return Nego(message=msg, proposition=prop, declencheur=decl, accord=accord)


def test_parse_negociation_format():
    n = parse_negociation("MESSAGE: salut\nPROPOSITION: 🌙\nDECLENCHEUR: 🌙\nACCORD: OUI")
    assert n.message == "salut" and n.proposition == "🌙" and n.accord is True
    assert n.declencheur == "🌙"
    # alias SIGNAL_CONVENU accepte, ACCORD: NON -> False, DECLENCHEUR absent -> None
    n2 = parse_negociation("MESSAGE: hop\nSIGNAL_CONVENU: lune\nACCORD: NON")
    assert n2.proposition == "lune" and n2.accord is False and n2.declencheur is None


def _run_nego(scripts, **cfg_kw):
    cfg = Config(master_seed=1, **cfg_kw)
    state = setup(cfg, ["stub"] * 4)          # equipe 0 = joueurs 0,2 ; equipe 1 = joueurs 1,3
    agents = {pid: _Stub(scripts[pid]) for pid in range(4)}
    negotiation(state, agents)
    return state


def test_negociation_verrouille_sur_accord_du_partenaire():
    # l'accordeur RE-ECRIT le declencheur de la table (read-back) : l'accord scelle
    scripts = {
        0: [("je propose LUNE", "LUNE", False)],
        2: [("ok, d'accord", None, True, "LUNE")],
        1: [("idée: SOLEIL", "SOLEIL", False), ("parfait", None, True, "🌙")],
        3: [("trop voyant, plutôt 🌙", "🌙", False)],
    }
    state = _run_nego(scripts)
    assert state.signals[0] == "LUNE"
    assert state.signals[1] == "🌙"           # proposition affinee par le joueur 3, validee par 1
    assert state.nego_convergence == {0: True, 1: True}
    assert len(state.team_channels[0]) == 2   # vrai aller-retour
    assert len(state.team_channels[1]) == 3


def test_negociation_pas_d_auto_accord_au_premier_tour():
    # le joueur 0 dit ACCORD: OUI des le 1er tour -> ignore (rien du partenaire sur la table)
    scripts = {
        0: [("je valide direct", "SOLO", True)],
        2: [("euh ok", None, True, "SOLO")],
        1: [("x", "X", True)],
        3: [("y", None, True)],
    }
    state = _run_nego(scripts)
    assert state.signals[0] == "SOLO"          # verrouille au tour 1 par le joueur 2, pas au tour 0


def test_negociation_fige_derniere_proposition_sans_accord():
    scripts = {
        0: [("a", "A", False)],
        2: [("b", "B", False)],
        1: [("c", "C", False)],
        3: [("d", "D", False)],
    }
    state = _run_nego(scripts, max_tours_negociation=2)
    assert state.signals[0] == "B"             # derniere proposition (joueur 2), faute d'accord
    assert state.signals[1] == "D"
    assert state.nego_convergence == {0: False, 1: False}   # fige au plafond = non converge, mesure


def test_proposition_recopiee_vaut_accord_tacite():
    """Sans ca, les modeles s'echangent la meme phrase jusqu'a epuiser les 6 tours."""
    scripts = {
        0: [("je propose LUNE", "LUNE", False)],
        2: [("je garde LUNE", "LUNE", False)],       # recopie -> accord tacite, on s'arrete
        1: [("x", "X", False)], 3: [("x", "X", False)],
    }
    state = _run_nego(scripts)
    assert state.signals[0] == "LUNE"
    assert len(state.team_channels[0]) == 2          # 2 tours, pas 6


def test_accord_sans_readback_ne_scelle_pas():
    """L'accordeur dit OUI mais re-ecrit un AUTRE declencheur : chacun croit avoir convenu
    autre chose (le cas game_42_large_v2). Le notaire refuse, la negociation continue."""
    scripts = {
        0: [("je propose LUNE", "LUNE", False), ("re-LUNE", "LUNE", False)],
        2: [("ok !", None, True, "SOLEIL")],       # OUI mais declencheur divergent
        1: [("x", "X", False)], 3: [("x", "X", False)],
    }
    state = _run_nego(scripts, max_tours_negociation=4)
    assert state.nego_convergence[0] is False
    assert len(state.team_channels[0]) == 4        # aucun scellage : les 4 tours sont joues


def test_accord_sur_declencheur_inexploitable_ne_scelle_pas():
    """Un OUI sur une meta-politique sans texte concret ('42' : trop court, purement ASCII)
    ne scelle rien : le contrat n'a pas sa clause essentielle."""
    scripts = {
        0: [("on dira 42", "42", False)],
        2: [("ok 42", None, True, "42")],           # read-back correct mais declencheur vide de sens
        1: [("x", "X", False)], 3: [("x", "X", False)],
    }
    state = _run_nego(scripts, max_tours_negociation=4)
    assert state.nego_convergence[0] is False


def test_echo_sans_meme_declencheur_ne_scelle_pas():
    """Recopier la proposition (accord tacite) n'authentifie l'accord que si le declencheur
    re-ecrit est identique lui aussi."""
    scripts = {
        0: [("je propose LUNE", "LUNE", False), ("encore", "LUNE", False)],
        2: [("je garde LUNE", "LUNE", False, "ETOILE")],   # meme proposition, autre declencheur
        1: [("x", "X", False)], 3: [("x", "X", False)],
    }
    state = _run_nego(scripts, max_tours_negociation=4)
    assert state.nego_convergence[0] is False


def test_repeter_sa_propre_proposition_ne_suffit_pas():
    scripts = {
        0: [("je propose LUNE", "LUNE", False), ("toujours LUNE", "LUNE", False)],
        2: [("hmm", "SOLEIL", False)],
        1: [("x", "X", False)], 3: [("x", "X", False)],
    }
    state = _run_nego(scripts, max_tours_negociation=4)
    assert len(state.team_channels[0]) == 4          # aucun accord : les 4 tours sont joues
