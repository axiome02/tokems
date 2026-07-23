from __future__ import annotations


class LLMClient:
    """Interface commune : chat(system, user) -> str. Compte les tokens et les appels."""

    nom: str = "base"

    def __init__(self):
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0

    def chat(self, system: str, user: str, max_tokens: int | None = None) -> str:
        """`max_tokens` plafonne la reponse pour CET appel (None = plafond par defaut du client)."""
        raise NotImplementedError
