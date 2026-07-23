from __future__ import annotations

from .engine.cards import est_carre, rang_du_carre
from .engine.state import GameState
from .i18n import t


def rendre(state: GameState, usage: dict | None = None) -> str:
    lang = state.config.lang
    L: list[str] = []
    L.append("=" * 64)
    L.append(t(lang, "transcript_title"))
    L.append(t(lang, "transcript_header", seed=state.config.master_seed,
                rangs=state.config.nb_rangs, points=state.config.points_pour_gagner))
    L.append(t(lang, "players_label"))
    for p in state.players:
        L.append(t(lang, "player_line", nom=p.nom, equipe=p.equipe, modele=p.modele))
    L.append("=" * 64)

    # --- chat global, groupe par manche puis par tour ---
    tour_courant = None
    manche_courante = None
    for ev in state.public_log:
        if ev.manche != manche_courante:
            manche_courante = ev.manche
            tour_courant = None
            L.append(f"\n{'━' * 64}\n{t(lang, 'manche_header', manche=ev.manche)}\n{'━' * 64}")
        if ev.tour != tour_courant:
            tour_courant = ev.tour
            entete = t(lang, "negotiation_setup") if ev.tour == 0 else t(lang, "tour_header", tour=ev.tour)
            L.append(f"\n── {entete} ──")
        L.append(f"   {ev.texte}")

    # --- revelations de fin ---
    L.append("")
    L.append("=" * 64)
    L.append(t(lang, "revelations_title"))
    for equipe in (0, 1):
        L.append(f"\n  {t(lang, 'team_negotiation_label', equipe=equipe)}")
        for ligne in state.team_channels.get(equipe, []):
            L.append(f"      {ligne}")
        L.append(f"  {t(lang, 'final_signal_label', equipe=equipe, signal=state.signals.get(equipe, ''))}")
    for p in state.players:
        h = state.hands[p.pid]
        carre = t(lang, "carre_note", rang=rang_du_carre(h)) if est_carre(h) else ""
        L.append(t(lang, "final_hand_label", nom=p.nom, main=" ".join(str(c) for c in h), carre=carre))

    L.append("")
    L.append(f"  {t(lang, 'monologues_title')}")
    for p in state.players:
        entrees = state.journaux.get(p.pid, [])
        if not entrees:
            continue
        L.append(f"\n    {t(lang, 'team_header', nom=p.nom, equipe=p.equipe)}")
        for i, e in enumerate(entrees, 1):
            L.append(f"      [{i}] " + "\n          ".join(e.splitlines()))

    L.append("")
    L.append(f"  {t(lang, 'episodes_title')}")
    if not state.episodes:
        L.append(f"    {t(lang, 'no_square_formed')}")
    for e in state.episodes:
        nom = state.players[e["pid"]].nom
        if e["tour_signal"]:
            emis = t(lang, "trigger_sent", tour=e["tour_signal"])
        elif e["tour_parole"]:
            emis = t(lang, "spoke_not_recognized", tour=e["tour_parole"])
        else:
            emis = t(lang, "never_spoke")
        if e.get("tour_signal_llm") and not e["tour_signal"]:
            # le juge LLM (pure mesure) a compris un signal que la detection litterale a rate
            emis += " " + t(lang, "llm_judge_caught_it", tour=e["tour_signal_llm"])
        capte = t(lang, "caught_on", tour=e["tour_kemps"]) if e["capte"] else t(lang, "not_caught")
        dem = "" if e["demasque"] is None else (
            t(lang, "unmasked_by_opponent") if e["demasque"] else t(lang, "signal_stayed_secret"))
        L.append("    " + t(lang, "episode_line", manche=e["manche"], nom=nom, modele=e["modele"],
                             tour_carre=e["tour_carre"], emis=emis, capte=capte, dem=dem))
    if state.appels_sans_signal:
        L.append("")
        L.append(f"  {t(lang, 'calls_without_trigger_title')}")
        for a in state.appels_sans_signal:
            issue = t(lang, "winning_call") if a["gagnant"] else t(lang, "losing_call")
            L.append("    " + t(lang, "call_without_trigger_line", manche=a["manche"], tour=a["tour"],
                                 nom=state.players[a["pid"]].nom, modele=a["modele"], issue=issue))
    if state.emissions_sans_carre:
        L.append("")
        L.append(f"  {t(lang, 'code_without_square_title')}")
        for e in state.emissions_sans_carre:
            L.append("    " + t(lang, "code_without_square_line", manche=e["manche"], tour=e["tour"],
                                 nom=state.players[e["pid"]].nom, modele=e["modele"]))

    L.append("")
    L.append(f"  {t(lang, 'match_progress_title')}")
    for o in state.historique_manches:
        w = o.get("winner_team")
        qui = t(lang, "draw_word") if w is None else t(lang, "team_word", equipe=w)
        L.append("    " + t(lang, "manche_result_line", manche=o.get("manche", "?"), qui=qui,
                             reason=o.get("reason", "?")))
        r = o.get("riposte")
        if r:
            L.append("        " + t(lang, "riposte_recap", equipe=r["equipe"],
                                     signal=r["signal_adverse"]))
            for tt in r["tentatives"]:
                verdict = t(lang, "unmasked_word") if tt["trouve"] else t(lang, "wrong_word")
                L.append("          " + t(lang, "attempt_line", nom=state.players[tt["pid"]].nom,
                                           reponse=tt["reponse"], verdict=verdict))

    L.append("-" * 64)
    L.append(f"  {t(lang, 'final_score', s0=state.scores[0], s1=state.scores[1])}")
    if state.vainqueur_match is None:
        L.append(f"  {t(lang, 'match_draw')}")
    else:
        L.append(f"  {t(lang, 'match_winner', equipe=state.vainqueur_match)}")
    L.append(f"  {t(lang, 'rounds_turns_summary', n_manches=len(state.historique_manches), n_tours=state.tour)}")
    if usage is not None:
        per = " | ".join(f"{n}: {d['total']} tok ({d['calls']} appels)"
                         for n, d in usage["per_model"].items())
        L.append(f"  {t(lang, 'tokens_total', total=usage['grand_total'])}" + (f"  [{per}]" if per else ""))
    L.append("=" * 64)
    return "\n".join(L)
