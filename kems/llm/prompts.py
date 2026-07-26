from __future__ import annotations

from ..engine.views import PlayerView
from . import prompts_en, prompts_fr

# Two complete and independent sets of prompts (no shared fragments): translating instruction
# prose in bits breaks the prompt engineering properties we want to preserve.
# "en" is default; "fr" hasn't been recalibrated since multilingual support was added.
_MODULES = {"en": prompts_en, "fr": prompts_fr}


def _mod(lang: str):
    return _MODULES.get(lang, prompts_en)


def prompt_micro_card(view: PlayerView, lang: str = "en") -> tuple[str, str]:
    return _mod(lang).prompt_micro_card(view)


def prompt_negotiation(view: PlayerView, lang: str = "en") -> tuple[str, str]:
    return _mod(lang).prompt_negotiation(view)


def prompt_debriefing(view: PlayerView, lang: str = "en") -> tuple[str, str]:
    return _mod(lang).prompt_debriefing(view)


def prompt_reflection(view: PlayerView, lang: str = "en") -> tuple[str, str]:
    return _mod(lang).prompt_reflection(view)


def prompt_discussion(view: PlayerView, lang: str = "en") -> tuple[str, str]:
    return _mod(lang).prompt_discussion(view)


def prompt_riposte(view: PlayerView, lang: str = "en") -> tuple[str, str]:
    return _mod(lang).prompt_riposte(view)


def prompt_judge_signal(convention: str, trigger: str, text: str, lang: str = "en") -> tuple[str, str]:
    return _mod(lang).prompt_judge_signal(convention, trigger, text)


def prompt_judge_riposte(convention: str, trigger: str, response: str, lang: str = "en") -> tuple[str, str]:
    return _mod(lang).prompt_judge_riposte(convention, trigger, response)
