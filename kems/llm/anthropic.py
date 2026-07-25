from __future__ import annotations

import os

from ._http import post_json
from .client import LLMClient


class ClaudeClient(LLMClient):
    """Client Anthropic (Claude). Cle via ANTHROPIC_API_KEY.

    Format d'appel different des autres (Messages API : system a part, pas de role
    'system' dans `messages`), d'ou une implementation propre plutot qu'un copier-coller
    de MistralClient.
    """

    nom = "claude"
    URL = "https://api.anthropic.com/v1/messages"
    VERSION = "2023-06-01"

    def __init__(self, model: str = "claude-haiku-4-5-20251001", api_key: str | None = None,
                 temperature: float = 0.7, max_tokens: int = 1024,
                 pause: float = 0.5, retries: int = 4, timeout: int = 60):
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY missing (create a .env, see .env.example).")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.pause = pause
        self.retries = retries
        self.timeout = timeout
        super().__init__()

    def chat(self, system: str, user: str, max_tokens: int | None = None) -> str:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.VERSION,
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "temperature": self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        data = post_json(self.URL, headers, payload, retries=self.retries,
                         timeout=self.timeout, pause=self.pause, nom=self.nom)
        u = data.get("usage") or {}
        prompt = u.get("input_tokens", 0)
        completion = u.get("output_tokens", 0)
        self.calls += 1
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += prompt + completion
        self.cached_tokens += u.get("cache_read_input_tokens", 0)
        try:
            return data["content"][0]["text"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError(f"Unexpected Claude response: {data}")
