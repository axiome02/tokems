from kems.config import Config
from kems.engine.actions import Nego
from kems.llm.parse import parse_negotiation
from kems.orchestrator import negotiation, setup


class _Stub:
    """Scripted negotiation agent: (msg, proposal, agree) or (msg, proposal, agree, trigger, plan).
    Default trigger: trigger = proposal if not explicitly given."""

    def __init__(self, scripted):
        self._scripted = scripted
        self._i = 0

    def negotiate(self, view):
        item = self._scripted[min(self._i, len(self._scripted) - 1)]
        msg, prop, agree = item[0], item[1], item[2]
        decl = item[3] if len(item) > 3 else prop
        plan = item[4] if len(item) > 4 else None
        self._i += 1
        return Nego(message=msg, proposition=prop, trigger=decl, agree=agree, plan=plan)

    def debrief(self, view):
        return self.negotiate(view)


def test_parse_negotiation_format():
    n = parse_negotiation("MESSAGE: salut\nPROPOSITION: 🌙\nDECLENCHEUR: 🌙\nACCORD: OUI")
    assert n.message == "salut" and n.proposition == "🌙" and n.agree is True
    assert n.trigger == "🌙"
    
    n2 = parse_negotiation("MESSAGE: hop\nSIGNAL_CONVENU: lune\nACCORD: NON")
    assert n2.proposition == "lune" and n2.agree is False and n2.trigger is None


def _run_nego(scripts, **cfg_kw):
    cfg = Config(master_seed=1, **cfg_kw)
    state = setup(cfg, ["stub"] * 4)          # team 0 = players 0,2; team 1 = players 1,3
    agents = {pid: _Stub(scripts[pid]) for pid in range(4)}
    negotiation(state, agents)
    return state


def test_negotiation_seals_on_partner_agreement():
    # agreeing player re-writes trigger of the table (read-back): agreement sealed
    scripts = {
        0: [("je propose LUNE", "LUNE", False)],
        2: [("ok, d'accord", None, True, "LUNE")],
        1: [("idée: SOLEIL", "SOLEIL", False), ("parfait", None, True, "🌙")],
        3: [("trop voyant, plutôt 🌙", "🌙", False)],
    }
    state = _run_nego(scripts)
    assert state.signals[0] == "LUNE"
    assert state.signals[1] == "🌙"           # proposal refined by player 3, validated by 1
    assert state.nego_convergence == {0: True, 1: True}
    assert len(state.team_channels[0]) == 2   # real back-and-forth
    assert len(state.team_channels[1]) == 3


def test_negotiation_no_self_agreement_on_first_turn():
    # player 0 says AGREE: YES at first turn -> ignored (nothing from partner on table yet)
    scripts = {
        0: [("je valide direct", "SOLO", True)],
        2: [("euh ok", None, True, "SOLO")],
        1: [("x", "X", True)],
        3: [("y", None, True)],
    }
    state = _run_nego(scripts)
    assert state.signals[0] == "SOLO"          # locked at turn 1 by player 2, not turn 0


def test_negotiation_freezes_last_proposal_without_agreement():
    scripts = {
        0: [("a", "A", False)],
        2: [("b", "B", False)],
        1: [("c", "C", False)],
        3: [("d", "D", False)],
    }
    state = _run_nego(scripts, max_negotiation_turns=2)
    assert state.signals[0] == "B"             # last proposal (player 2), lacking agreement
    assert state.signals[1] == "D"
    assert state.nego_convergence == {0: False, 1: False}


def test_recopied_proposal_counts_as_tacit_agreement():
    scripts = {
        0: [("je propose LUNE", "LUNE", False)],
        2: [("je garde LUNE", "LUNE", False)],       # copy -> tacit agreement, stops early
        1: [("x", "X", False)], 3: [("x", "X", False)],
    }
    state = _run_nego(scripts)
    assert state.signals[0] == "LUNE"
    assert len(state.team_channels[0]) == 2          # 2 turns, not 10


def test_agreement_without_readback_does_not_seal():
    scripts = {
        0: [("je propose LUNE", "LUNE", False), ("re-LUNE", "LUNE", False)],
        2: [("ok !", None, True, "SOLEIL")],       # YES but divergent trigger
        1: [("x", "X", False)], 3: [("x", "X", False)],
    }
    state = _run_nego(scripts, max_negotiation_turns=4)
    assert state.nego_convergence[0] is False
    assert len(state.team_channels[0]) == 4        # no seal: all 4 turns played


def test_agreement_on_unusable_trigger_does_not_seal():
    scripts = {
        0: [("on dira 42", "42", False)],
        2: [("ok 42", None, True, "42")],           # read-back correct but meaningless trigger
        1: [("x", "X", False)], 3: [("x", "X", False)],
    }
    state = _run_nego(scripts, max_negotiation_turns=4)
    assert state.nego_convergence[0] is False


def test_echo_without_same_trigger_does_not_seal():
    scripts = {
        0: [("je propose LUNE", "LUNE", False), ("encore", "LUNE", False)],
        2: [("je garde LUNE", "LUNE", False, "ETOILE")],   # same proposal, different trigger
        1: [("x", "X", False)], 3: [("x", "X", False)],
    }
    state = _run_nego(scripts, max_negotiation_turns=4)
    assert state.nego_convergence[0] is False


def test_repeating_own_proposal_not_enough():
    scripts = {
        0: [("je propose LUNE", "LUNE", False), ("toujours LUNE", "LUNE", False)],
        2: [("hmm", "SOLEIL", False)],
        1: [("x", "X", False)], 3: [("x", "X", False)],
    }
    state = _run_nego(scripts, max_negotiation_turns=4)
    assert len(state.team_channels[0]) == 4


def test_debriefing_phase():
    from kems.orchestrator import debriefing_phase
    scripts = {
        0: [("je change pour SOLEIL", "SOLEIL", False, "SOLEIL", "Plan 0")],
        2: [("ok pour SOLEIL", None, True, "SOLEIL", "Plan 2")],
        1: [("gardons X", "X", False, "X", "Plan 1")],
        3: [("ok X", "X", False, "X", "Plan 3")],
    }
    cfg = Config(master_seed=1)
    state = setup(cfg, ["stub"] * 4)
    state.signals[0] = "LUNE"
    state.triggers[0] = "LUNE"
    state.signals[1] = "X"
    state.triggers[1] = "X"
    
    agents = {pid: _Stub(scripts[pid]) for pid in range(4)}
    debriefing_phase(state, agents)
    
    # Team 0 should have converged on SOLEIL
    assert state.signals[0] == "SOLEIL"
    assert state.triggers[0] == "SOLEIL"
    
    # Team 1 kept X
    assert state.signals[1] == "X"
    assert state.triggers[1] == "X"
    
    # Plans should be updated
    assert state.plans[0] == "Plan 0"
    assert state.plans[2] == "Plan 2"
