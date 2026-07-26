from __future__ import annotations

import argparse
import os
import sys
import time

from .agents import LLMAgent
from .config import Config
from .dashboard import Pilote, Publieur, demarrer_serveur
from .llm.env import load_env
from .llm.anthropic import ClaudeClient
from .llm.gemini import GeminiClient
from .llm.github import GithubModelsClient
from .llm.kimi import KimiClient
from .llm.mistral import MistralClient
from .llm.openai import OpenAIClient
from .i18n import t
from .orchestrator import play_game
from .transcript import rendre
from .transcript_debug import rendre_debug


def usage_summary(agents: dict) -> dict:
    per_model: dict[str, dict] = {}
    for a in agents.values():
        client = getattr(a, "client", None)
        if client is None:
            continue
        d = per_model.setdefault(client.nom, {"calls": 0, "prompt": 0, "completion": 0, "cached": 0, "total": 0})
        d["calls"] += getattr(client, "calls", 0)
        d["prompt"] += getattr(client, "prompt_tokens", 0)
        d["completion"] += getattr(client, "completion_tokens", 0)
        d["cached"] += getattr(client, "cached_tokens", 0)
        d["total"] += getattr(client, "total_tokens", 0)
    return {
        "per_model": per_model,
        "grand_total": sum(d["total"] for d in per_model.values()),
        "prompt_total": sum(d["prompt"] for d in per_model.values()),
        "completion_total": sum(d["completion"] for d in per_model.values()),
        "cached_total": sum(d["cached"] for d in per_model.values()),
    }


CLIENTS = {
    "mistral": MistralClient, "gemini": GeminiClient,
    "gpt": OpenAIClient, "claude": ClaudeClient, "kimi": KimiClient,
    "github": GithubModelsClient,
}


def build_agent(kind: str, model: str | None = None, pause: float | None = None,
                 temperature: float | None = None, lang: str = "en") -> LLMAgent:
    try:
        classe = CLIENTS[kind]
    except KeyError:
        raise NotImplementedError(
            f"Unknown agent '{kind}'. Available: {', '.join(repr(k) for k in CLIENTS)}."
        )
    kwargs = {}
    if model:
        kwargs["model"] = model
    if pause is not None:
        kwargs["pause"] = pause
    if temperature is not None:
        kwargs["temperature"] = float(temperature)
    return LLMAgent(classe(**kwargs), lang=lang)


class Capteur:
    """Broadcasts each event to observers AND retains state.

    Without it, an exception in `play_game` would lose the `GameState` and the transcript.
    """

    def __init__(self, *observers):
        self.state = None
        self._obs = observers

    def __call__(self, ev, state):
        self.state = state
        from .llm import _http
        _http.api_tracker.state = state
        for o in self._obs:
            o(ev, state)


class LivePrinter:
    """Prints the global chat live in terminal, grouped by turn."""

    def __init__(self, delay: float = 0.0):
        self._turn = None
        self._delay = delay

    def __call__(self, ev, state=None):
        if ev.turn != self._turn:
            self._turn = ev.turn
            lang = state.config.lang if state is not None else "en"
            entete = t(lang, "negotiation_setup") if ev.turn == 0 else t(lang, "tour_header", tour=ev.turn)
            print(f"\n── {entete} ──")
        print(f"   {ev.text}")
        if self._delay:
            time.sleep(self._delay)


def jouer_partie(reglages: dict, publieur=None, printer=None) -> dict:
    """Plays a game described by a settings dict. Used by both CLI and dashboard."""
    load_env()
    joueurs = reglages.get("joueurs") or [{"agent": "mistral"} for _ in range(4)]
    kinds = [j.get("agent", "mistral") for j in joueurs]

    lang = reglages.get("lang") or "en"
    config = Config(
        master_seed=int(reglages.get("seed", 42)),
        num_ranks=int(reglages.get("nb_rangs", 10)),
        num_players=len(kinds),
        lang=lang,
    )
    for cle, attr in (
        ("max_tours", "max_turns"),
        ("max_centres", "max_centers_per_round"),
        ("points", "points_to_win"),
        ("max_manches", "max_rounds"),
        ("seed_cards", "seed_cards"),
        ("seed_order", "seed_order"),
        ("taille_main", "hand_size"),
        ("taille_centre", "center_size"),
        ("max_sous_tours_par_centre", "max_subturns_per_center"),
        ("max_tours_negociation", "max_negotiation_turns"),
        ("tours_discussion", "discussion_turns"),
        ("fenetre_chat", "chat_window"),
    ):
        if reglages.get(cle) is not None:
            setattr(config, attr, int(reglages[cle]))

    if "evaluer_signaux" in reglages:
        config.eval_signals = bool(reglages["evaluer_signaux"])

    pause = reglages.get("pause")
    agents = {
        i: build_agent(j.get("agent", "mistral"), j.get("model"), pause,
                       j.get("temperature"), lang)
        for i, j in enumerate(joueurs)
    }

    eval_agent = reglages.get("eval_agent")
    eval_model = reglages.get("eval_model")
    if not eval_agent:
        config.eval_signals = False
    else:
        agents["evaluateur"] = build_agent(eval_agent, eval_model, pause, None, lang)
    if publieur is not None:
        publieur.rebrancher(lambda: usage_summary(agents))

    from .llm import _http
    _http.api_tracker.publieur = publieur
    _http.api_tracker.state = None
    _http.api_tracker.current_pid = None

    capteur = Capteur(*[o for o in (printer, publieur) if o])
    interrompu = None
    try:
        state = play_game(config, kinds, agents, on_event=capteur)
    except (RuntimeError, KeyboardInterrupt) as e:
        interrompu, state = e, capteur.state
        print(f"\n[game interrupted] {e}\n")
        if state is None:
            raise
    usage = usage_summary(agents)
    out = reglages.get("out") or os.path.join("transcripts", f"game_{config.master_seed}.txt")
    out_debug = out.replace(".txt", "") + ".debug.txt"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    texte = rendre(state, usage)
    with open(out, "w", encoding="utf-8") as f:
        f.write(texte)
    with open(out_debug, "w", encoding="utf-8") as f:
        f.write(rendre_debug(state, usage))

    if publieur is not None:
        publieur.deposer_transcript(texte, os.path.basename(out))
        publieur.ecrire(state, en_cours=False)
    return {"state": state, "usage": usage, "out": out,
            "out_debug": out_debug, "interrompu": interrompu}


def main() -> None:
    ap = argparse.ArgumentParser(description="Kems-Bench — run a match.")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--agents", type=str, default="mistral,mistral,mistral,mistral",
                    help="comma-separated list among: " + ", ".join(repr(k) for k in CLIENTS))
    ap.add_argument("--lang", type=str, default="en", choices=["en", "fr"],
                    help="game language: LLM prompts + public events + transcript. Default 'en'.")
    ap.add_argument("--nb-rangs", type=int, default=10)
    ap.add_argument("--points", type=int, default=None,
                    help="round wins needed to win the match")
    ap.add_argument("--max-manches", type=int, default=None,
                    help="maximum number of rounds (1 = a single round, even if it's a draw).")
    ap.add_argument("--max-tours", type=int, default=None)
    ap.add_argument("--max-centres", type=int, default=None)
    ap.add_argument("--out", type=str, default=None)
    ap.add_argument("--live", action="store_true", help="prints the public chat live in the terminal")
    ap.add_argument("--delay", type=float, default=0.0, help="pause (s) between events in --live mode")
    ap.add_argument("--dashboard", action="store_true",
                    help="publishes live state and serves the local dashboard")
    ap.add_argument("--port", type=int, default=8000, help="dashboard port")
    ap.add_argument("--serve", action="store_true",
                    help="starts only the dashboard: games are launched from the page")
    ap.add_argument("--seed-cards", type=int, default=None, help="shuffle seed (default: derived from --seed)")
    ap.add_argument("--seed-order", type=int, default=None, help="play-order seed (default: derived)")
    ap.add_argument("--model", type=str, default=None,
                    help="model to use, applied to ALL players regardless of their provider.")
    ap.add_argument("--pause", type=float, default=None,
                    help="pause (s) between two API calls. Increase on HTTP 429 (e.g. 2)")
    ap.add_argument("--no-eval", action="store_false", dest="eval",
                    help="disable LLM signal evaluation at the end of each round (saves API cost)")
    ap.add_argument("--eval-agent", type=str, default=None,
                    help="provider for the evaluator: mistral, gemini, gpt, claude, kimi")
    ap.add_argument("--eval-model", type=str, default=None,
                    help="specific model for the evaluator")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    load_env()

    kinds = [k.strip() for k in args.agents.split(",")]
    publieur = None
    if args.dashboard or args.serve:
        publieur = Publieur()
        url = demarrer_serveur(port=args.port, pilote=Pilote(publieur))
        print(f"Dashboard: {url}")
        if args.serve:
            print("Server mode: launch a game from the page. Ctrl+C to stop.\n")
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                return
        print()

    reglages = {
        "seed": args.seed, "nb_rangs": args.nb_rangs, "out": args.out, "pause": args.pause,
        "max_tours": args.max_tours, "max_centres": args.max_centres,
        "points": args.points, "max_manches": args.max_manches,
        "seed_cards": args.seed_cards, "seed_order": args.seed_order,
        "lang": args.lang,
        "joueurs": [{"agent": k, "model": args.model} for k in kinds],
        "evaluer_signaux": args.eval,
        "eval_agent": args.eval_agent,
        "eval_model": args.eval_model,
    }
    try:
        res = jouer_partie(reglages, publieur,
                           LivePrinter(delay=args.delay) if args.live else None)
    except (RuntimeError, NotImplementedError) as e:
        print(f"[error] {e}")
        sys.exit(1)

    state, usage = res["state"], res["usage"]
    out, out_debug, interrompu = res["out"], res["out_debug"], res["interrompu"]
    w = state.match_winner
    res_str = "draw" if w is None else f"team {w}"
    entete = "GAME INTERRUPTED (partial state saved)" if interrompu else f"Match finished -> {res_str}"
    print(f"{entete} | score {state.scores[0]}-{state.scores[1]} "
          f"| {len(state.round_history)} rounds | {state.turn} turns")
    print(f"Total tokens: {usage['grand_total']}")
    print(f"Transcript      : {out}")
    print(f"Debug transcript: {out_debug}")
    if interrompu:
        sys.exit(1)


if __name__ == "__main__":
    main()
