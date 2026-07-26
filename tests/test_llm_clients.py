import os

from kems.llm.anthropic import ClaudeClient
from kems.llm.client import LLMClient
from kems.llm.env import load_env
from kems.llm.gemini import GeminiClient
from kems.llm.github import GithubModelsClient
from kems.llm.kimi import KimiClient
from kems.llm.mistral import MistralClient
from kems.llm.openai import OpenAIClient
from kems.llm.openrouter import OpenRouterClient


def test_load_env(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text('FOO_KEY=abc123\n# commentaire\nBAR="ok"\n', encoding="utf-8")
    monkeypatch.delenv("FOO_KEY", raising=False)
    monkeypatch.delenv("BAR", raising=False)
    load_env(str(f))
    assert os.environ["FOO_KEY"] == "abc123"
    assert os.environ["BAR"] == "ok"


def test_load_env_nexplose_pas_si_absent():
    load_env("fichier_qui_nexiste_pas.env")  # ne doit pas lever


def test_clients_sont_des_llmclient():
    m = MistralClient(api_key="fake")
    g = GeminiClient(api_key="fake")
    o = OpenAIClient(api_key="fake")
    c = ClaudeClient(api_key="fake")
    k = KimiClient(api_key="fake")
    gh = GithubModelsClient(api_key="fake")
    or_c = OpenRouterClient(api_key="fake")
    for client in (m, g, o, c, k, gh, or_c):
        assert isinstance(client, LLMClient)
    assert (m.nom, g.nom, o.nom, c.nom, k.nom, gh.nom, or_c.nom) == ("mistral", "gemini", "gpt", "claude", "kimi", "github", "openrouter")


def test_client_sans_cle_leve(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    try:
        MistralClient()
        assert False, "aurait du lever RuntimeError"
    except RuntimeError as e:
        assert "MISTRAL_API_KEY" in str(e)


def test_nouveaux_clients_sans_cle_levent(monkeypatch):
    for env_key, classe in (
        ("OPENAI_API_KEY", OpenAIClient),
        ("ANTHROPIC_API_KEY", ClaudeClient),
        ("KIMI_API_KEY", KimiClient),
        ("GITHUB_TOKEN", GithubModelsClient),
        ("OPENROUTER_API_KEY", OpenRouterClient),
    ):
        monkeypatch.delenv(env_key, raising=False)
        try:
            classe()
            assert False, f"{classe.__name__} aurait du lever RuntimeError"
        except RuntimeError as e:
            assert env_key in str(e)

