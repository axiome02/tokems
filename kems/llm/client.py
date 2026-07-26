from __future__ import annotations


class LLMClient:
    """Common interface: chat(system, user) -> str. Counts tokens and calls."""

    nom: str = "base"

    def __init__(self):
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cached_tokens = 0
        self.total_tokens = 0

    def chat(self, system: str, user: str, max_tokens: int | None = None) -> str:
        """`max_tokens` limits the response length for THIS call (None = client's default limit)."""
        raise NotImplementedError
