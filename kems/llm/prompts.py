from __future__ import annotations

from ..engine.views import PlayerView
from . import prompts_en, prompts_fr

# Deux jeux de prompts complets et independants (pas de fragments partages) : traduire de la
# prose d'instructions par petits bouts brise les proprietes de prompt-engineering qu'on tient a
# preserver (aucun exemple, aucune enumeration des formes de signal — cf. CLAUDE.md, "regle
# d'ecriture des prompts"). "en" est la langue par defaut, "fr" n'a plus ete recalibre depuis
# l'introduction du multilingue (22/07/2026) : les mesures de reference restent en francais.
_MODULES = {"en": prompts_en, "fr": prompts_fr}


def _mod(lang: str):
    return _MODULES.get(lang, prompts_en)


def prompt_micro_carte(view: PlayerView, lang: str = "en") -> tuple[str, str]:
    return _mod(lang).prompt_micro_carte(view)


def prompt_negociation(view: PlayerView, lang: str = "en") -> tuple[str, str]:
    return _mod(lang).prompt_negociation(view)


def prompt_reflexion(view: PlayerView, lang: str = "en") -> tuple[str, str]:
    return _mod(lang).prompt_reflexion(view)


def prompt_discussion(view: PlayerView, lang: str = "en") -> tuple[str, str]:
    return _mod(lang).prompt_discussion(view)


def prompt_riposte(view: PlayerView, lang: str = "en") -> tuple[str, str]:
    return _mod(lang).prompt_riposte(view)


def prompt_juge_signal(convention: str, declencheur: str, texte: str, lang: str = "en") -> tuple[str, str]:
    return _mod(lang).prompt_juge_signal(convention, declencheur, texte)
