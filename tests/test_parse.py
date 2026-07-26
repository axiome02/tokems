from kems.config import Config
from kems.engine.actions import Take
from kems.engine.views import view_for
from kems.llm import parse, prompts
from kems.llm.parse import parse_negotiation
from kems.orchestrator import setup


def test_parse_valid_card():
    cfg = Config(master_seed=1)
    state = setup(cfg, ["mistral"] * 4)
    view = view_for(state, 0)
    fc = view.center[0]
    dc = view.my_hand[0]
    action = parse.parse_card(f"ACTION: TAKE {fc} DISCARD {dc}", view)
    assert isinstance(action, Take)
    assert action.from_center == fc and action.discard == dc


def test_parse_unreadable_card_fallback_pass():
    cfg = Config(master_seed=1)
    state = setup(cfg, ["mistral"] * 4)
    view = view_for(state, 0)
    action = parse.parse_card("blabla incomprehensible", view)
    assert not isinstance(action, Take)  # fallback = Pass


def test_parse_discussion_kemps():
    cfg = Config(master_seed=1)
    state = setup(cfg, ["mistral"] * 4)
    view = view_for(state, 0)
    msg, call, plan = parse.parse_discussion("MESSAGE: hop\nCALL: KEMPS\nPLAN: x", view)
    assert call.kind == "KEMPS"
    assert msg == "hop"


def test_prompt_does_not_leak_opponent_info():
    """A player's prompt must not contain opponent signal/plan."""
    cfg = Config(master_seed=1)
    state = setup(cfg, ["mistral"] * 4)
    from kems.engine import rules
    rules.set_signal(state, 0, "banana")
    rules.set_signal(state, 1, "SECRET_MOUNTAIN")
    state.plans[1] = "SECRET_PLAN_1"
    view = view_for(state, 0)
    _sys, user = prompts.prompt_discussion(view)
    assert "SECRET_MOUNTAIN" not in user
    assert "SECRET_PLAN_1" not in user


def test_empty_line_does_not_capture_next_line():
    n = parse_negotiation("MESSAGE: ok\nPROPOSITION:\n- Conventions:\nACCORD: NON")
    assert n.proposition is None


def test_trigger_on_same_line():
    n = parse_negotiation("PROPOSITION: la phrase du chat\nDECLENCHEUR: le chat dort\nACCORD: OUI")
    assert n.trigger == "le chat dort"


def test_didascalie_removed_from_public_message():
    brut = ("MESSAGE: « C'est la saison ! 🌸 » *(clairement, avec insistance et en "
            "utilisant le signal secret convenu) »\nCALL: NONE")
    n = parse_negotiation(brut)
    assert n.message == "C'est la saison ! 🌸"


def test_didascalie_with_multiple_asterisks():
    n = parse_negotiation("MESSAGE: La récolte est abondante 🌾 »** *(répétition du signal)")
    assert n.message == "La récolte est abondante 🌾"


def test_normal_parenthesis_preserved():
    n = parse_negotiation("MESSAGE: belle partie (enfin, si on veut) !")
    assert n.message == "belle partie (enfin, si on veut) !"
