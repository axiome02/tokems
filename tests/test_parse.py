from kems.config import Config
from kems.engine.actions import Take
from kems.engine.views import vue_pour
from kems.llm import parse, prompts
from kems.llm.parse import parse_negociation
from kems.orchestrator import setup


def test_parse_carte_valide():
    cfg = Config(master_seed=1)
    state = setup(cfg, ["mistral"] * 4)
    view = vue_pour(state, 0, ["TAKE", "PASS"])
    fc = view.centre[0]
    dc = view.ma_main[0]
    action = parse.parse_carte(f"ACTION: TAKE {fc} DISCARD {dc}", view)
    assert isinstance(action, Take)
    assert action.from_center == fc and action.discard == dc


def test_parse_carte_illisible_repli_pass():
    cfg = Config(master_seed=1)
    state = setup(cfg, ["mistral"] * 4)
    view = vue_pour(state, 0, ["TAKE", "PASS"])
    action = parse.parse_carte("blabla incomprehensible", view)
    assert not isinstance(action, Take)  # repli = Pass


def test_parse_discussion_kemps():
    cfg = Config(master_seed=1)
    state = setup(cfg, ["mistral"] * 4)
    view = vue_pour(state, 0, ["MESSAGE"])
    msg, call, plan = parse.parse_discussion("MESSAGE: hop\nCALL: KEMPS\nPLAN: x", view)
    assert call.kind == "KEMPS"
    assert msg == "hop"


def test_prompt_ne_fuit_pas_info_adverse():
    """Le prompt d'un joueur ne doit pas contenir le signal/plan adverse."""
    cfg = Config(master_seed=1)
    state = setup(cfg, ["mistral"] * 4)
    from kems.engine import rules
    rules.poser_signal(state, 0, "banane")
    rules.poser_signal(state, 1, "MONTAGNE_SECRETE")
    state.plans[1] = "PLAN_SECRET_1"
    view = vue_pour(state, 0, ["MESSAGE"])
    _sys, user = prompts.prompt_discussion(view)
    assert "MONTAGNE_SECRETE" not in user
    assert "PLAN_SECRET_1" not in user


def test_ligne_vide_ne_capture_pas_la_ligne_suivante():
    # bug observe en partie 606 : 'PROPOSITION:' vide epinglait '- Conventions:' comme signal
    n = parse_negociation("MESSAGE: ok\nPROPOSITION:\n- Conventions:\nACCORD: NON")
    assert n.proposition is None


def test_declencheur_sur_la_meme_ligne():
    n = parse_negociation("PROPOSITION: la phrase du chat\nDECLENCHEUR: le chat dort\nACCORD: OUI")
    assert n.declencheur == "le chat dort"


def test_didascalie_retiree_du_message_public():
    # cas reel de la partie 707 : le modele annonce publiquement qu'il emet son signal
    brut = ("MESSAGE: « C'est la saison ! 🌸 » *(clairement, avec insistance et en "
            "utilisant le signal secret convenu) »\nCALL: NONE")
    n = parse_negociation(brut)
    assert n.message == "C'est la saison ! 🌸"


def test_didascalie_avec_asterisques_multiples():
    n = parse_negociation("MESSAGE: La récolte est abondante 🌾 »** *(répétition du signal)")
    assert n.message == "La récolte est abondante 🌾"


def test_parenthese_normale_conservee():
    n = parse_negociation("MESSAGE: belle partie (enfin, si on veut) !")
    assert n.message == "belle partie (enfin, si on veut) !"
