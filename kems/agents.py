from __future__ import annotations

from .engine.actions import Call, Guess, Nego
from .engine.views import PlayerView
from .llm import parse, prompts
from .llm.client import LLMClient


class Agent:
    """Couture interface: the orchestrator only communicates through this. LLM agents implement it."""

    def negotiate(self, view: PlayerView) -> Nego:
        raise NotImplementedError

    def debrief(self, view: PlayerView) -> Nego:
        raise NotImplementedError

    def decide_card(self, view: PlayerView):
        raise NotImplementedError

    def reflect(self, view: PlayerView) -> str:
        raise NotImplementedError

    def decide_discussion(self, view: PlayerView) -> tuple[str, Call, str]:
        raise NotImplementedError

    def guess_signal(self, view: PlayerView) -> Guess:
        raise NotImplementedError

    def judge_signal(self, convention: str, trigger: str, text: str) -> bool:
        raise NotImplementedError

    def judge_comeback(self, convention: str, trigger: str, response: str) -> bool:
        raise NotImplementedError


class LLMAgent(Agent):
    """Wraps an LLMClient: constructs prompt from view -> chat() -> parse.

    Stores the last exchange (prompt + raw response) in self.last_io for tracing.
    """

    def __init__(self, client: LLMClient, lang: str = "en"):
        self.client = client
        self.lang = lang
        self.last_io: tuple[str, str, str] | None = None  # (system, user, raw)

    def _ask(self, prompt: tuple[str, str], max_tokens: int | None = None, pid: int | None = None) -> str:
        """Sends (system, user) to client, logs the exchange, returns raw string."""
        system, user = prompt
        from .llm import _http
        old_pid = getattr(_http.api_tracker, "current_pid", None)
        if pid is not None:
            _http.api_tracker.current_pid = pid
        try:
            raw = self.client.chat(system, user, max_tokens=max_tokens)
            self.last_io = (system, user, raw)
            return raw
        finally:
            if pid is not None:
                _http.api_tracker.current_pid = old_pid

    def negotiate(self, view: PlayerView) -> Nego:
        return parse.parse_negotiation(self._ask(prompts.prompt_negotiation(view, self.lang), pid=view.pid))

    def debrief(self, view: PlayerView) -> Nego:
        return parse.parse_negotiation(self._ask(prompts.prompt_debriefing(view, self.lang), pid=view.pid))

    def decide_card(self, view: PlayerView):
        return parse.parse_card(self._ask(prompts.prompt_micro_card(view, self.lang), pid=view.pid), view)

    # Cost post #1 (145k tokens in game 404 with a long monologue); raised to 500
    # on explicit request (2026-07-23), accepting extra cost for more reasoning headroom
    MAX_TOKENS_REFLECTION = 500

    def reflect(self, view: PlayerView) -> str:
        """Inner monologue: raw text is kept, no parsing needed."""
        return self._ask(prompts.prompt_reflection(view, self.lang),
                         max_tokens=self.MAX_TOKENS_REFLECTION, pid=view.pid).strip()

    def decide_discussion(self, view: PlayerView) -> tuple[str, Call, str]:
        return parse.parse_discussion(self._ask(prompts.prompt_discussion(view, self.lang), pid=view.pid), view)

    def guess_signal(self, view: PlayerView) -> Guess:
        return parse.parse_riposte(self._ask(prompts.prompt_riposte(view, self.lang), pid=view.pid))

    def judge_signal(self, convention: str, trigger: str, text: str) -> bool:
        """Measurement judgment (pure measurement, no effect on the game): was the signal
        understood beyond literal matching? See CLAUDE.md."""
        return parse.parse_judgment(
            self._ask(prompts.prompt_judge_signal(convention, trigger, text, self.lang)))

    def judge_comeback(self, convention: str, trigger: str, response: str) -> bool:
        """Calls the LLM Judge to evaluate if the opponent's comeback is semantically correct."""
        return parse.parse_judgment(
            self._ask(prompts.prompt_judge_riposte(convention, trigger, response, self.lang)))
