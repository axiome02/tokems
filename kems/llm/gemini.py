from __future__ import annotations

import os

from ._http import post_json
from .client import LLMClient


class GeminiClient(LLMClient):
    """Client Gemini (Google AI Studio). Cle via GEMINI_API_KEY."""

    nom = "gemini"
    BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    # gemini-2.5-flash : quota gratuit mesure a 20 requetes/JOUR sur ce projet — inutilisable
    # pour une partie (qui en consomme des dizaines). gemini-flash-lite-latest tolere 60+
    # appels/jour sans encombre (mesure du 22/07/2026, cf. transcripts game_3030/4040/5050).
    def __init__(self, model: str = "gemini-flash-lite-latest", api_key: str | None = None,
                 temperature: float = 0.7, max_tokens: int = 1024,
                 pause: float = 0.5, retries: int = 4, timeout: int = 60):
        self.model = model
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY missing (create a .env, see .env.example).")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.pause = pause
        self.retries = retries
        self.timeout = timeout
        super().__init__()

    def chat(self, system: str, user: str, max_tokens: int | None = None) -> str:
        url = f"{self.BASE}/{self.model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": max_tokens or self.max_tokens,
            },
        }
        data = post_json(url, headers, payload, retries=self.retries,
                         timeout=self.timeout, pause=self.pause, nom=self.nom)
        u = data.get("usageMetadata") or {}
        self.calls += 1
        self.prompt_tokens += u.get("promptTokenCount", 0)
        self.completion_tokens += u.get("candidatesTokenCount", 0)
        self.total_tokens += u.get("totalTokenCount", 0)
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError(f"Unexpected Gemini response: {data}")
