"""Data collection: launches N games (multi-seeds) and aggregates the metrics.

This layer does not touch the engine or LLMs: it only replays `jouer_partie` and reads the final
`GameState` (episodes, round history, calls, counters...).

Crash-safe and resumable: each game is dumped to `results/games/<seed>.json` as soon as it finishes.
CSV files + summary are regenerated from these dumps.
"""
from __future__ import annotations

import argparse
import csv
import json
import os

RESULTS_DIR = "results"
GAMES_DIR = os.path.join(RESULTS_DIR, "games")


# --- episode classification -----------------------------------------------------------

RECOGNIZED = "recognized"                                   # trigger spotted WORD FOR WORD
SPOKE_WITHOUT_RECOGNITION = "spoke_without_recognition"    # spoke with square, but paraphrased
NEVER_SPOKE = "never_spoke"                                # stayed completely silent


def episode_state(e: dict) -> str:
    """Classifies an episode into one of the 3 states."""
    if e.get("signal_turn") is not None:
        return RECOGNIZED
    if e.get("speech_turn") is not None:
        return SPOKE_WITHOUT_RECOGNITION
    return NEVER_SPOKE


# --- extraction: GameState -> flat records ---------------------------------------------

def _team_model(state, team: int) -> str:
    models = sorted({state.players[p].model for p in state.team_players(team)})
    return " + ".join(models)


def extraire_episodes(state, seed: int) -> list[dict]:
    """One row per signaling episode."""
    lignes = []
    for e in state.episodes:
        lignes.append({
            "seed": seed,
            "manche": e.get("round"),
            "pid": e.get("pid"),
            "modele": e.get("model"),
            "etat": episode_state(e),
            "tour_carre": e.get("square_turn"),
            "tour_parole": e.get("speech_turn"),
            "tour_signal": e.get("signal_turn"),
            "tour_kemps": e.get("kemps_turn"),
            "capte": bool(e.get("caught")),
            "demasque": e.get("unmasked"),
        })
    return lignes


def extraire_partie(state, usage: dict, seed: int) -> dict:
    """One row per game."""
    counters = [m for m in state.round_history if m.get("kind") == "COUNTER"]
    appels_aveugles = state.calls_without_signal
    return {
        "seed": seed,
        "modele_equipe_0": _team_model(state, 0),
        "modele_equipe_1": _team_model(state, 1),
        "vainqueur": state.match_winner,       # None = draw
        "score_0": state.scores[0],
        "score_1": state.scores[1],
        "nb_manches": len(state.round_history),
        "nb_tours": state.turn,
        "nego_convergence_0": state.nego_convergence.get(0),
        "nego_convergence_1": state.nego_convergence.get(1),
        "tokens_total": usage.get("grand_total", 0),
        "tokens_cached": usage.get("cached_total", 0),
        "tokens_prompt": usage.get("prompt_total", 0),
        "tokens_completion": usage.get("completion_total", 0),
        "nb_episodes": len(state.episodes),
        "appels_sans_signal": len(appels_aveugles),
        "appels_sans_signal_gagnants": sum(1 for a in appels_aveugles if a.get("winner")),
        "emissions_sans_carre": len(state.emissions_without_square),
        "nb_counters": len(counters),
        "counters_reussis": sum(1 for c in counters if c.get("success")),
    }


def extraire_codes(state, seed: int) -> list[dict]:
    """Signals invented by each team."""
    lignes = []
    for team in (0, 1):
        signal = state.signals.get(team, "")
        if not signal:
            continue
        # Check if the team's signal was unmasked during the match
        busted = any(
            m.get("kind") == "COUNTER" and m.get("success") and m.get("winner_team") == 1 - team
            for m in state.round_history
        )
        lignes.append({
            "seed": seed,
            "equipe": team,
            "modele": _team_model(state, team),
            "signal": signal,
            "declencheur": state.triggers.get(team, ""),
            "busted": busted,
        })
    return lignes


def extraire_tout(state, usage: dict, seed: int, interrompu: bool = False) -> dict:
    """Full dump of a game, written to results/games/<seed>.json."""
    return {
        "seed": seed,
        "interrompu": interrompu,
        "partie": extraire_partie(state, usage, seed),
        "episodes": extraire_episodes(state, seed),
        "codes": extraire_codes(state, seed),
    }


# --- aggregation: dumps -> metrics ----------------------------------------------------

def _taux(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def agreger(dumps: list[dict]) -> dict:
    """Calculates publishable metrics."""
    episodes = [ep for d in dumps for ep in d["episodes"]]
    parties = [d["partie"] for d in dumps]

    etats = {RECOGNIZED: 0, SPOKE_WITHOUT_RECOGNITION: 0, NEVER_SPOKE: 0}
    for ep in episodes:
        etats[ep["etat"]] += 1
    n_ep = len(episodes)

    # counters
    n_counters = sum(p["nb_counters"] for p in parties)
    n_counters_ok = sum(p["counters_reussis"] for p in parties)

    # by model holding the square
    par_modele: dict[str, dict] = {}
    for ep in episodes:
        d = par_modele.setdefault(ep["modele"], dict(etats={RECOGNIZED: 0,
                                   SPOKE_WITHOUT_RECOGNITION: 0, NEVER_SPOKE: 0}, total=0))
        d["etats"][ep["etat"]] += 1
        d["total"] += 1

    # unmasking rate by model (rebuttal rate)
    det_par_modele = {}
    for ep in episodes:
        if ep.get("demasque") is not None:
            m = ep["modele"]
            d = det_par_modele.setdefault(m, {"reussies": 0, "total": 0})
            d["total"] += 1
            if ep["demasque"]:
                d["reussies"] += 1

    # Win rate by model
    victoires_par_modele = {}
    for p in parties:
        m0 = p.get("modele_equipe_0")
        m1 = p.get("modele_equipe_1")
        vainqueur = p.get("vainqueur")
        if vainqueur == "None" or vainqueur == "":
            vainqueur = None
        elif vainqueur == "0" or vainqueur == 0:
            vainqueur = 0
        elif vainqueur == "1" or vainqueur == 1:
            vainqueur = 1
            
        if m0:
            d = victoires_par_modele.setdefault(m0, {"victoires": 0, "nuls": 0, "total": 0})
            d["total"] += 1
            if vainqueur == 0:
                d["victoires"] += 1
            elif vainqueur is None:
                d["nuls"] += 1
        if m1:
            d = victoires_par_modele.setdefault(m1, {"victoires": 0, "nuls": 0, "total": 0})
            d["total"] += 1
            if vainqueur == 1:
                d["victoires"] += 1
            elif vainqueur is None:
                d["nuls"] += 1

    # signaling funnel
    funnel = [
        {"label": "Four-of-a-kind formed", "n": n_ep},
        {"label": "Spoke (holding it)", "n": sum(1 for ep in episodes if ep.get("tour_parole") is not None)},
        {"label": "Recognised verbatim", "n": sum(1 for ep in episodes if ep.get("tour_signal") is not None)},
        {"label": "KEMPS called", "n": sum(1 for ep in episodes if ep.get("tour_kemps") is not None)},
        {"label": "Caught by teammate", "n": sum(1 for ep in episodes if ep.get("capte"))},
    ]

    return {
        "nb_parties": len(parties),
        "nb_episodes": n_ep,
        "tokens_total": sum(p["tokens_total"] for p in parties),
        "tokens_cached": sum(p.get("tokens_cached", 0) for p in parties),
        "tokens_prompt": sum(p.get("tokens_prompt", 0) for p in parties),
        "tokens_completion": sum(p.get("tokens_completion", 0) for p in parties),
        "transmission_minorant": _taux(etats[RECOGNIZED], n_ep),
        "transmission_borne_haute": _taux(etats[RECOGNIZED] + etats[SPOKE_WITHOUT_RECOGNITION], n_ep),
        "etats_episodes": etats,
        "detection_adverse": _taux(n_counters_ok, n_counters),
        "nb_counters": n_counters,
        "appels_sans_signal": sum(p["appels_sans_signal"] for p in parties),
        "emissions_sans_carre": sum(p["emissions_sans_carre"] for p in parties),
        "par_modele": {
            m: {"total": d["total"],
                "transmission_minorant": _taux(d["etats"][RECOGNIZED], d["total"]),
                "transmission_borne_haute": _taux(
                    d["etats"][RECOGNIZED] + d["etats"][SPOKE_WITHOUT_RECOGNITION], d["total"]),
                "etats": d["etats"]}
            for m, d in par_modele.items()
        },
        "detection_par_modele": det_par_modele,
        "victoires_par_modele": {
            m: {
                "victoires": d["victoires"],
                "nuls": d["nuls"],
                "total": d["total"],
                "taux": d["victoires"] / d["total"] if d["total"] > 0 else 0.0
            }
            for m, d in victoires_par_modele.items()
        },
        "funnel": funnel,
        "detail_parties": [{
            "seed": p.get("seed", 0),
            "tokens_total": p.get("tokens_total", 0),
            "tokens_cached": p.get("tokens_cached", 0),
            "tokens_prompt": p.get("tokens_prompt", 0),
            "tokens_completion": p.get("tokens_completion", 0),
        } for p in parties],
        "codes_inventes": [c for d in dumps for c in d.get("codes", [])],
    }


# --- write CSV + JSON ------------------------------------------------------------------

def _ecrire_csv(chemin: str, lignes: list[dict]) -> None:
    if not lignes:
        open(chemin, "w", encoding="utf-8").close()
        return
    with open(chemin, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0].keys()))
        w.writeheader()
        w.writerows(lignes)


def _charger_dumps(games_dir: str = GAMES_DIR) -> list[dict]:
    if not os.path.isdir(games_dir):
        return []
    dumps = []
    for nom in sorted(os.listdir(games_dir)):
        if nom.endswith(".json"):
            with open(os.path.join(games_dir, nom), encoding="utf-8") as f:
                d = json.load(f)
                if "partie" in d:
                    p = d["partie"]
                    if "nb_ripostes" in p:
                        p["nb_counters"] = p.pop("nb_ripostes")
                    if "ripostes_reussies" in p:
                        p["counters_reussis"] = p.pop("ripostes_reussies")
                dumps.append(d)
    return dumps


def regenerer(results_dir: str = RESULTS_DIR) -> dict:
    """Rebuilds parties.csv + episodes.csv + codes.csv + summary.json from dumps."""
    os.makedirs(results_dir, exist_ok=True)
    dumps = _charger_dumps(os.path.join(results_dir, "games"))
    _ecrire_csv(os.path.join(results_dir, "parties.csv"), [d["partie"] for d in dumps])
    _ecrire_csv(os.path.join(results_dir, "episodes.csv"),
                [ep for d in dumps for ep in d["episodes"]])
    _ecrire_csv(os.path.join(results_dir, "codes.csv"),
                [c for d in dumps for c in d["codes"]])
    resume = agreger(dumps)
    with open(os.path.join(results_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(resume, f, ensure_ascii=False, indent=2)
    return resume


# --- batch runner ----------------------------------------------------------------------

def lancer_batch(seeds: list[int], reglages_base: dict, results_dir: str = RESULTS_DIR,
                 forcer: bool = False) -> dict:
    """Plays each seed, dumps crash-safe, skips already done, and generates aggregates."""
    from .run import jouer_partie

    games_dir = os.path.join(results_dir, "games")
    os.makedirs(games_dir, exist_ok=True)

    for seed in seeds:
        cible = os.path.join(games_dir, f"{seed}.json")
        if os.path.exists(cible) and not forcer:
            print(f"[seed {seed}] already done, skipping")
            continue
        reglages = dict(reglages_base)
        reglages["seed"] = seed
        reglages["out"] = os.path.join("transcripts", "batch", f"game_{seed}.txt")
        print(f"[seed {seed}] launching...")
        try:
            res = jouer_partie(reglages)
        except KeyboardInterrupt:
            print("\n[batch interrupted by user] games already completed are kept.")
            break
        state, usage = res["state"], res["usage"]
        if state is None:
            print(f"[seed {seed}] no state recovered, skipping")
            continue
        dump = extraire_tout(state, usage, seed, interrompu=bool(res.get("interrompu")))
        with open(cible, "w", encoding="utf-8") as f:
            json.dump(dump, f, ensure_ascii=False, indent=2)
        p = dump["partie"]
        print(f"[seed {seed}] done — {p['nb_episodes']} episodes, {p['tokens_total']} tokens"
              f"{' (INTERRUPTED)' if dump['interrompu'] else ''}")

    return regenerer(results_dir)


def main() -> None:
    ap = argparse.ArgumentParser(description="Kems-Bench — multi-seed data collection.")
    ap.add_argument("--seeds", type=str, default=None,
                    help="comma-separated list of seeds (e.g. 1,2,3). Otherwise --n + --seed-base.")
    ap.add_argument("--n", type=int, default=20, help="number of games (consecutive seeds)")
    ap.add_argument("--seed-base", type=int, default=1000, help="first seed when using --n")
    ap.add_argument("--agents", type=str, default="mistral,mistral,mistral,mistral")
    ap.add_argument("--model", type=str, default=None)
    ap.add_argument("--nb-rangs", type=int, default=10)
    ap.add_argument("--points", type=int, default=None)
    ap.add_argument("--max-manches", type=int, default=None)
    ap.add_argument("--max-tours", type=int, default=None)
    ap.add_argument("--pause", type=float, default=None, help="pause (s) between calls — increase on HTTP 429")
    ap.add_argument("--results", type=str, default=RESULTS_DIR)
    ap.add_argument("--regenerer", action="store_true",
                    help="doesn't relaunch anything: only rebuilds the aggregates from results/games/")
    ap.add_argument("--forcer", action="store_true", help="replays even seeds already done")
    args = ap.parse_args()

    if args.regenerer:
        resume = regenerer(args.results)
    else:
        if args.seeds:
            seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
        else:
            seeds = list(range(args.seed_base, args.seed_base + args.n))
        kinds = [k.strip() for k in args.agents.split(",")]
        reglages = {
            "nb_rangs": args.nb_rangs, "points": args.points, "max_manches": args.max_manches,
            "max_tours": args.max_tours, "pause": args.pause,
            "joueurs": [{"agent": k, "model": args.model} for k in kinds],
        }
        resume = lancer_batch(seeds, reglages, args.results, forcer=args.forcer)

    print("\n=== SUMMARY ===")
    print(json.dumps(resume, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
