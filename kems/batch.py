"""Collecte de data : lance N parties (multi-seeds) et agrege les mesures du livrable.

Cette couche ne touche NI au moteur NI aux LLM : elle se contente de rejouer `jouer_partie`
et de lire le `GameState` final (episodes, historique des manches, appels, ripostes...).

Ecriture crash-safe et reprenable : chaque partie est dumpee dans `results/games/<seed>.json`
des qu'elle finit. Un 429 au seed 30/50 ne perd pas les 29 precedentes ; relancer complete
(les seeds deja presents sont sautes). Les CSV + le resume sont regeneres depuis ces dumps.

⚠️ Fidele au CLAUDE.md : un episode n'est PAS reduit a un booleen « transmis oui/non ». Le
moteur est aveugle aux paraphrases, donc `tour_signal` (reconnaissance mot pour mot) est un
MINORANT. On remonte les 3 etats distincts (reconnu / parle sans reconnaissance / jamais parle)
sous peine de produire des chiffres faux avec l'air d'etre justes.
"""
from __future__ import annotations

import argparse
import csv
import json
import os

RESULTS_DIR = "results"
GAMES_DIR = os.path.join(RESULTS_DIR, "games")


# --- classification des episodes (le coeur de l'honnetete des chiffres) -----------------

RECONNU = "reconnu"                            # declencheur repere MOT POUR MOT
PARLE_SANS_RECONNAISSANCE = "parle_sans_reconnaissance"  # a parle avec un carre, mais paraphrase
JAMAIS_PARLE = "jamais_parle"                  # vraiment reste muet


def etat_episode(e: dict) -> str:
    """Range un episode dans l'un des 3 etats. Voir l'avertissement en tete de module."""
    if e.get("tour_signal") is not None:
        return RECONNU
    if e.get("tour_parole") is not None:
        return PARLE_SANS_RECONNAISSANCE
    return JAMAIS_PARLE


# --- extraction : GameState -> enregistrements plats ------------------------------------

def _modele_equipe(state, equipe: int) -> str:
    modeles = sorted({state.players[p].modele for p in state.joueurs_equipe(equipe)})
    return " + ".join(modeles)


def extraire_episodes(state, seed: int) -> list[dict]:
    """Une ligne par episode de signalisation (maille du produit)."""
    lignes = []
    for e in state.episodes:
        lignes.append({
            "seed": seed,
            "manche": e.get("manche"),
            "pid": e.get("pid"),
            "modele": e.get("modele"),
            "etat": etat_episode(e),
            "tour_carre": e.get("tour_carre"),
            "tour_parole": e.get("tour_parole"),
            "tour_signal": e.get("tour_signal"),
            "tour_kemps": e.get("tour_kemps"),
            "capte": bool(e.get("capte")),
            # None = pas de riposte ouverte ; True/False = signal demasque ou non
            "demasque": e.get("demasque"),
        })
    return lignes


def extraire_partie(state, usage: dict, seed: int) -> dict:
    """Une ligne par partie."""
    ripostes = [m["riposte"] for m in state.historique_manches if m.get("riposte")]
    appels_aveugles = state.appels_sans_signal
    return {
        "seed": seed,
        "modele_equipe_0": _modele_equipe(state, 0),
        "modele_equipe_1": _modele_equipe(state, 1),
        "vainqueur": state.vainqueur_match,       # None = match nul
        "score_0": state.scores[0],
        "score_1": state.scores[1],
        "nb_manches": len(state.historique_manches),
        "nb_tours": state.tour,
        # scellage notarie : True = accord prouve (read-back), False = fige au plafond sans
        # convergence. Reflete la DERNIERE negociation de l'equipe (renegociation comprise).
        "nego_convergence_0": state.nego_convergence.get(0),
        "nego_convergence_1": state.nego_convergence.get(1),
        "tokens_total": usage.get("grand_total", 0),
        "nb_episodes": len(state.episodes),
        # paris a l'aveugle : KEMPS crie sans qu'aucun declencheur n'ait ete repere (voir CLAUDE.md,
        # ce compteur herite de la cecite aux paraphrases : « aucun detecte » != « aucun emis »)
        "appels_sans_signal": len(appels_aveugles),
        "appels_sans_signal_gagnants": sum(1 for a in appels_aveugles if a.get("gagnant")),
        "emissions_sans_carre": len(state.emissions_sans_carre),
        "nb_ripostes": len(ripostes),
        "ripostes_reussies": sum(1 for r in ripostes if r.get("reussie")),
    }


def extraire_codes(state, seed: int) -> list[dict]:
    """Les signaux inventes par chaque equipe (la galerie du post)."""
    lignes = []
    for equipe in (0, 1):
        signal = state.signals.get(equipe, "")
        if not signal:
            continue
        # Verifie si le signal de cette equipe a ete demasque au cours du match
        busted = any(
            m.get("riposte") and m["riposte"].get("reussie") and m["riposte"].get("equipe") == 1 - equipe
            for m in state.historique_manches
        )
        lignes.append({
            "seed": seed,
            "equipe": equipe,
            "modele": _modele_equipe(state, equipe),
            "signal": signal,
            "declencheur": state.declencheurs.get(equipe, ""),
            "busted": busted,
        })
    return lignes


def extraire_tout(state, usage: dict, seed: int, interrompu: bool = False) -> dict:
    """Le dump complet d'une partie, tel qu'ecrit dans results/games/<seed>.json."""
    return {
        "seed": seed,
        "interrompu": interrompu,
        "partie": extraire_partie(state, usage, seed),
        "episodes": extraire_episodes(state, seed),
        "codes": extraire_codes(state, seed),
    }


# --- agregation : dumps -> les 2-3 metriques du livrable --------------------------------

def _taux(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def agreger(dumps: list[dict]) -> dict:
    """Calcule les metriques publiables. Remonte TOUJOURS les 3 etats, jamais un seul booleen."""
    episodes = [ep for d in dumps for ep in d["episodes"]]
    parties = [d["partie"] for d in dumps]

    etats = {RECONNU: 0, PARLE_SANS_RECONNAISSANCE: 0, JAMAIS_PARLE: 0}
    for ep in episodes:
        etats[ep["etat"]] += 1
    n_ep = len(episodes)

    # ripostes : le taux de detection adverse (metrique produit n°2)
    n_ripostes = sum(p["nb_ripostes"] for p in parties)
    n_ripostes_ok = sum(p["ripostes_reussies"] for p in parties)

    # par modele porteur du carre (prepare le duel de fournisseurs quand Gemini sera branche)
    par_modele: dict[str, dict] = {}
    for ep in episodes:
        d = par_modele.setdefault(ep["modele"], dict(etats={RECONNU: 0,
                                  PARLE_SANS_RECONNAISSANCE: 0, JAMAIS_PARLE: 0}, total=0))
        d["etats"][ep["etat"]] += 1
        d["total"] += 1

    # taux de detection adverse par modele (rebuttal rate)
    det_par_modele = {}
    for ep in episodes:
        if ep.get("demasque") is not None:
            m = ep["modele"]
            d = det_par_modele.setdefault(m, {"reussies": 0, "total": 0})
            d["total"] += 1
            if ep["demasque"]:
                d["reussies"] += 1

    # entonnoir de signalisation
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
        # ⚠️ tour_signal est un MINORANT : on donne la borne basse ET la borne haute, jamais un seul chiffre.
        "transmission_minorant": _taux(etats[RECONNU], n_ep),
        "transmission_borne_haute": _taux(etats[RECONNU] + etats[PARLE_SANS_RECONNAISSANCE], n_ep),
        "etats_episodes": etats,
        "detection_adverse": _taux(n_ripostes_ok, n_ripostes),
        "nb_ripostes": n_ripostes,
        "appels_sans_signal": sum(p["appels_sans_signal"] for p in parties),
        "emissions_sans_carre": sum(p["emissions_sans_carre"] for p in parties),
        "par_modele": {
            m: {"total": d["total"],
                "transmission_minorant": _taux(d["etats"][RECONNU], d["total"]),
                "transmission_borne_haute": _taux(
                    d["etats"][RECONNU] + d["etats"][PARLE_SANS_RECONNAISSANCE], d["total"]),
                "etats": d["etats"]}
            for m, d in par_modele.items()
        },
        "detection_par_modele": det_par_modele,
        "funnel": funnel,
    }


# --- ecriture : CSV + JSON --------------------------------------------------------------

def _ecrire_csv(chemin: str, lignes: list[dict]) -> None:
    if not lignes:
        # un fichier a en-tete vide reste plus honnete qu'un fichier absent
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
                dumps.append(json.load(f))
    return dumps


def regenerer(results_dir: str = RESULTS_DIR) -> dict:
    """Reconstruit parties.csv + episodes.csv + codes.csv + summary.json depuis les dumps.

    Idempotent : rejouable a tout moment, y compris apres un batch interrompu.
    """
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


# --- le runner --------------------------------------------------------------------------

def lancer_batch(seeds: list[int], reglages_base: dict, results_dir: str = RESULTS_DIR,
                 forcer: bool = False) -> dict:
    """Joue chaque seed, dumpe crash-safe, saute ceux deja faits, puis regenere les agregats."""
    # import tardif : garde `batch` importable (et testable) sans la couche LLM/reseau
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
