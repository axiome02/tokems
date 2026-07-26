from kems.config import Config
from kems.engine import rules
from kems.engine.actions import Call
from kems.engine.cards import SUITS, Card
from kems.engine.signaux import normalize, signal_found
from kems.llm.parse import parse_riposte
from kems.orchestrator import setup


def _game_with_successful_kemps():
    """Team 0 wins on a successful KEMPS -> Team 1 comebacks aiming at signal « ☀️ »."""
    state = setup(Config(master_seed=1), ["bot"] * 4)
    state.hands[2] = [Card(5, c) for c in SUITS]      # square in player 0's partner's hand
    rules.set_signal(state, 0, "☀️")                   # the signal to unmask
    rules.set_signal(state, 1, "the word tranquille")
    rules._log(state, "MESSAGE", 2, "Player 3: « nice evening ☀️ »")   # arm the call
    rules.resolve_calls(state, {0: Call("KEMPS")}, [0, 1, 2, 3])
    return state


# ───────────────────────── signal arbitration (deterministic) ─────────────────────
def test_normalization_ignores_accents_casing_punctuation():
    assert normalize("  Le MOT « Tranquillé » ! ") == "le mot tranquille"


def test_signal_cited_in_a_phrase():
    assert signal_found("☀️", "they use the sun emoji ☀️")
    assert signal_found("tranquille", "I believe the word is 'tranquille'")


def test_bare_response_for_verbose_signal():
    assert signal_found("the word 'tranquille'", "tranquille")


def test_selector_variation_ignored():
    assert signal_found("☀️", "☀")


def test_wrong_response():
    assert not signal_found("☀️", "a word about the weather")
    assert not signal_found("tranquille", "calme")


def test_empty_or_absent_response_never_wins():
    assert not signal_found("☀️", "")
    assert not signal_found("", "☀️")
    assert not signal_found("<none>", "none")


def test_too_short_response_not_accepted():
    # 'of' is included in the signal but shows no deduction
    assert not signal_found("of course tranquille", "of")


# ───────────────────────────── opening the comeback ────────────────────────────
def test_successful_kemps_opens_losing_team_comeback():
    state = _game_with_successful_kemps()
    assert state.finished
    assert state.outcome["winner_team"] == 0
    assert state.comeback_team == 1


def test_failed_kemps_does_not_open_comeback():
    state = setup(Config(master_seed=1), ["bot"] * 4)
    state.hands[2] = [Card(1, "♠"), Card(2, "♥"), Card(3, "♦"), Card(4, "♣")]
    rules.set_signal(state, 0, "☀️")
    rules._log(state, "MESSAGE", 2, "Player 3: « nice evening ☀️ »")
    rules.resolve_calls(state, {0: Call("KEMPS")}, [0, 1, 2, 3])
    assert state.comeback_team is None


def test_counter_does_not_open_comeback():
    state = setup(Config(master_seed=1), ["bot"] * 4)
    state.hands[1] = [Card(5, c) for c in SUITS]
    rules.resolve_calls(state, {0: Call("COUNTER")}, [0, 1, 2, 3])
    assert state.outcome["winner_team"] == 0
    assert state.comeback_team is None


# ─────────────────────────── resolving the comeback ─────────────────────────────
def test_successful_comeback_reverses_the_round():
    state = _game_with_successful_kemps()
    rules.resolve_comeback(state, {1: "no idea", 3: "they slip the emoji ☀️"})
    assert state.outcome["winner_team"] == 1
    assert state.outcome["riposte"]["success"] is True
    assert state.players[3].name in state.outcome["reason"]  # names who unmasked the signal


def test_failed_comeback_leaves_initial_winner():
    state = _game_with_successful_kemps()
    rules.resolve_comeback(state, {1: "the word hello", 3: "something about the weather"})
    assert state.outcome["winner_team"] == 0
    assert state.outcome["riposte"]["success"] is False
    assert len(state.outcome["riposte"]["attempts"]) == 2


def test_comeback_consumed_only_once():
    state = _game_with_successful_kemps()
    rules.resolve_comeback(state, {1: "", 3: ""})
    assert state.comeback_team is None
    rules.resolve_comeback(state, {1: "☀️", 3: "☀️"})   # no effect
    assert state.outcome["winner_team"] == 0


# ──────────────────────────────── parsing ─────────────────────────────────────────
def test_parse_riposte_structured_line():
    txt = "RAISONNEMENT: le soleil revient trop souvent\nSIGNAL_ADVERSE: **☀️**"
    assert parse_riposte(txt).response == "☀️"


def test_parse_riposte_fallback_last_line():
    assert parse_riposte("I believe it is\nthe sun emoji").response == "the sun emoji"


def test_judge_comeback_prompts_and_parsing():
    from kems.llm.prompts import prompt_judge_riposte
    from kems.llm.parse import parse_judgment
    
    sys_fr, usr_fr = prompt_judge_riposte("banane", "banane", "ils disent banane", "fr")
    assert "CONVENTION SECRETE ADVERSE" in usr_fr
    
    sys_en, usr_en = prompt_judge_riposte("banana", "banana", "they say banana", "en")
    assert "OPPOSING SECRET CONVENTION" in usr_en
    
    assert parse_judgment("SIGNAL: OUI") is True
    assert parse_judgment("SIGNAL: YES") is True
    assert parse_judgment("SIGNAL: NON") is False
    assert parse_judgment("SIGNAL: NO") is False


def test_riposte_phase_with_llm_judge():
    from kems.orchestrator import riposte_phase
    
    class MockEvaluator:
        def __init__(self):
            self.calls = []
            
        def guess_signal(self, view):
            from kems.engine.actions import Guess
            if view.pid == 1:
                return Guess("soleil")
            return Guess("lune")
            
        def judge_comeback(self, convention, trigger, response):
            self.calls.append((convention, trigger, response))
            return response == "soleil"
            
    cfg = Config(master_seed=1)
    state = setup(cfg, ["bot"] * 4)
    state.comeback_team = 1
    state.outcome = {"winner_team": 0, "reason": "KEMPS reussi", "kind": "KEMPS"}
    state.signals[0] = "soleil"
    state.triggers[0] = "soleil"
    
    evaluator = MockEvaluator()
    agents = {0: evaluator, 1: evaluator, 2: evaluator, 3: evaluator, "evaluateur": evaluator}
    
    riposte_phase(state, agents)
    
    assert len(evaluator.calls) == 2
    assert evaluator.calls[0] == ("soleil", "soleil", "soleil")
    assert evaluator.calls[1] == ("soleil", "soleil", "lune")
    
    assert state.outcome["winner_team"] == 1
    assert state.outcome["riposte"]["success"] is True
