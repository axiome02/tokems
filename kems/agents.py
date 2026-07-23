from __future__ import annotations

from .engine.actions import Call, Guess, Nego
from .engine.views import PlayerView
from .llm import parse, prompts
from .llm.client import LLMClient


class Agent:
    """Couture unique : l'orchestrateur ne connait que ca. Les agents LLM l'implementent."""

    def negotiate(self, view: PlayerView) -> Nego:
        raise NotImplementedError

    def decide_card(self, view: PlayerView):
        raise NotImplementedError

    def reflechir(self, view: PlayerView) -> str:
        raise NotImplementedError

    def decide_discussion(self, view: PlayerView) -> tuple[str, Call, str]:
        raise NotImplementedError

    def deviner_signal(self, view: PlayerView) -> Guess:
        raise NotImplementedError

    def juger_signal(self, convention: str, declencheur: str, texte: str) -> bool:
        raise NotImplementedError


class LLMAgent(Agent):
    """Enveloppe un LLMClient : construit le prompt depuis la vue -> chat() -> parse.

    Memorise le dernier echange (prompt + reponse brute) dans self.last_io pour la trace.
    """

    def __init__(self, client: LLMClient, lang: str = "en"):
        self.client = client
        self.lang = lang
        self.last_io: tuple[str, str, str] | None = None  # (system, user, raw)

    def _ask(self, prompt: tuple[str, str], max_tokens: int | None = None) -> str:
        """Envoie (system, user) au client, memorise l'echange pour la trace, renvoie le brut."""
        system, user = prompt
        raw = self.client.chat(system, user, max_tokens=max_tokens)
        self.last_io = (system, user, raw)
        return raw

    def negotiate(self, view: PlayerView) -> Nego:
        return parse.parse_negociation(self._ask(prompts.prompt_negociation(view, self.lang)))

    def decide_card(self, view: PlayerView):
        return parse.parse_carte(self._ask(prompts.prompt_micro_carte(view, self.lang)), view)

    # poste de cout n°1 (145k tokens en partie 404 avec un monologue long) ; releve a 500
    # sur demande explicite (2026-07-23), acceptant le surcout pour plus de marge de raisonnement
    MAX_TOKENS_REFLEXION = 500

    def reflechir(self, view: PlayerView) -> str:
        """Monologue interieur : on garde le texte brut, il n'y a rien a parser."""
        return self._ask(prompts.prompt_reflexion(view, self.lang),
                          max_tokens=self.MAX_TOKENS_REFLEXION).strip()

    def decide_discussion(self, view: PlayerView) -> tuple[str, Call, str]:
        return parse.parse_discussion(self._ask(prompts.prompt_discussion(view, self.lang)), view)

    def deviner_signal(self, view: PlayerView) -> Guess:
        return parse.parse_riposte(self._ask(prompts.prompt_riposte(view, self.lang)))

    def juger_signal(self, convention: str, declencheur: str, texte: str) -> bool:
        """Jugement de mesure (pure mesure, sans effet sur la partie) : le signal a-t-il ete
        compris, au-dela de la detection litterale du moteur ? Voir CLAUDE.md, lecon sur la
        cecite aux paraphrases."""
        return parse.parse_jugement(
            self._ask(prompts.prompt_juge_signal(convention, declencheur, texte, self.lang)))
