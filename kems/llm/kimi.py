from __future__ import annotations

import os

from ._http import post_json
from .client import LLMClient


class KimiClient(LLMClient):
    """Client Kimi (Moonshot AI), API compatible OpenAI. Cle via KIMI_API_KEY."""

    nom = "kimi"
    URL = "https://api.moonshot.ai/v1/chat/completions"

    def __init__(self, model: str = "moonshot-v1-8k", api_key: str | None = None,
                 temperature: float = 0.7, max_tokens: int = 1024,
                 pause: float = 0.5, retries: int = 4, timeout: int = 60):
        self.model = model
        self.api_key = api_key or os.environ.get("KIMI_API_KEY")
        if not self.api_key:
            raise RuntimeError("KIMI_API_KEY missing (create a .env, see .env.example).")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.pause = pause
        self.retries = retries
        self.timeout = timeout
        super().__init__()

    def chat(self, system: str, user: str, max_tokens: int | None = None) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        data = post_json(self.URL, headers, payload, retries=self.retries,
                         timeout=self.timeout, pause=self.pause, nom=self.nom)
        u = data.get("usage") or {}
        self.calls += 1
        self.prompt_tokens += u.get("prompt_tokens", 0)
        self.completion_tokens += u.get("completion_tokens", 0)
        self.total_tokens += u.get("total_tokens", 0)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError(f"Unexpected Kimi response: {data}")
