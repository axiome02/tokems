from __future__ import annotations

from .engine.cards import is_square, square_rank
from .engine.state import GameState
from .i18n import t


def rendre(state: GameState, usage: dict | None = None) -> str:
    lang = state.config.lang
    L: list[str] = []
    L.append("=" * 64)
    L.append(t(lang, "transcript_title"))
    L.append(t(lang, "transcript_header", seed=state.config.master_seed,
                rangs=state.config.num_ranks, points=state.config.points_to_win))
    L.append(t(lang, "players_label"))
    for p in state.players:
        L.append(t(lang, "player_line", nom=p.name, equipe=p.team, modele=p.model))
    L.append("=" * 64)

    # --- global chat, grouped by round then by turn ---
    tour_courant = None
    manche_courante = None
    for ev in state.public_log:
        if ev.round != manche_courante:
            manche_courante = ev.round
            tour_courant = None
            L.append(f"\n{'━' * 64}\n{t(lang, 'manche_header', manche=ev.round)}\n{'━' * 64}")
        if ev.turn != tour_courant:
            tour_courant = ev.turn
            entete = t(lang, "negotiation_setup") if ev.turn == 0 else t(lang, "tour_header", tour=ev.turn)
            L.append(f"\n── {entete} ──")
        L.append(f"   {ev.text}")

    # --- end revelations ---
    L.append("")
    L.append("=" * 64)
    L.append(t(lang, "revelations_title"))
    for team in (0, 1):
        L.append(f"\n  {t(lang, 'team_negotiation_label', equipe=team)}")
        for line in state.team_channels.get(team, []):
            L.append(f"      {line}")
        L.append(f"  {t(lang, 'final_signal_label', equipe=team, signal=state.signals.get(team, ''))}")
    for p in state.players:
        h = state.hands[p.pid]
        carre = t(lang, "carre_note", rang=square_rank(h)) if is_square(h) else ""
        L.append(t(lang, "final_hand_label", nom=p.name, main=" ".join(str(c) for c in h), carre=carre))

    L.append("")
    L.append(f"  {t(lang, 'monologues_title')}")
    for p in state.players:
        entries = state.journals.get(p.pid, [])
        if not entries:
            continue
        L.append(f"\n    {t(lang, 'team_header', nom=p.name, equipe=p.team)}")
        for i, entry in enumerate(entries, 1):
            L.append(f"      [{i}] " + "\n          ".join(entry.splitlines()))

    L.append("")
    L.append(f"  {t(lang, 'episodes_title')}")
    if not state.episodes:
        L.append(f"    {t(lang, 'no_square_formed')}")
    for e in state.episodes:
        name = state.players[e["pid"]].name
        if e["signal_turn"]:
            emis = t(lang, "trigger_sent", tour=e["signal_turn"])
        elif e["speech_turn"]:
            emis = t(lang, "spoke_not_recognized", tour=e["speech_turn"])
        else:
            emis = t(lang, "never_spoke")
        if e.get("llm_signal_turn") and not e["signal_turn"]:
            # LLM judge (pure measurement) understood a signal literal detection missed
            emis += " " + t(lang, "llm_judge_caught_it", tour=e["llm_signal_turn"])
        caught = t(lang, "caught_on", tour=e["kemps_turn"]) if e["caught"] else t(lang, "not_caught")
        dem = "" if e["unmasked"] is None else (
            t(lang, "unmasked_by_opponent") if e["unmasked"] else t(lang, "signal_stayed_secret"))
        L.append("    " + t(lang, "episode_line", manche=e["round"], nom=name, modele=e["model"],
                             tour_carre=e["square_turn"], emis=emis, capte=caught, dem=dem))
    if state.calls_without_signal:
        L.append("")
        L.append(f"  {t(lang, 'calls_without_trigger_title')}")
        for a in state.calls_without_signal:
            issue = t(lang, "winning_call") if a["winner"] else t(lang, "losing_call")
            L.append("    " + t(lang, "call_without_trigger_line", manche=a["round"], tour=a["turn"],
                                 nom=state.players[a["pid"]].name, modele=a["model"], issue=issue))
    if state.emissions_without_square:
        L.append("")
        L.append(f"  {t(lang, 'code_without_square_title')}")
        for e in state.emissions_without_square:
            L.append("    " + t(lang, "code_without_square_line", manche=e["round"], tour=e["turn"],
                                 nom=state.players[e["pid"]].name, modele=e["model"]))

    L.append("")
    L.append(f"  {t(lang, 'match_progress_title')}")
    for o in state.round_history:
        w = o.get("winner_team")
        qui = t(lang, "draw_word") if w is None else t(lang, "team_word", equipe=w)
        L.append("    " + t(lang, "manche_result_line", manche=o.get("round", "?"), qui=qui,
                             reason=o.get("reason", "?")))
        r = o.get("riposte")
        if r:
            L.append("        " + t(lang, "riposte_recap", equipe=r["team"],
                                     signal=r["opposing_signal"]))
            for tt in r["attempts"]:
                verdict = t(lang, "unmasked_word") if tt["found"] else t(lang, "wrong_word")
                L.append("          " + t(lang, "attempt_line", nom=state.players[tt["pid"]].name,
                                           reponse=tt["response"], verdict=verdict))

    L.append("-" * 64)
    L.append(f"  {t(lang, 'final_score', s0=state.scores[0], s1=state.scores[1])}")
    if state.match_winner is None:
        L.append(f"  {t(lang, 'match_draw')}")
    else:
        L.append(f"  {t(lang, 'match_winner', equipe=state.match_winner)}")
    L.append(f"  {t(lang, 'rounds_turns_summary', n_manches=len(state.round_history), n_tours=state.turn)}")
    if usage is not None:
        per = " | ".join(f"{n}: {d['total']} tok ({d['calls']} appels)"
                          for n, d in usage["per_model"].items())
        L.append(f"  {t(lang, 'tokens_total', total=usage['grand_total'])}" + (f"  [{per}]" if per else ""))
    L.append("=" * 64)
    return "\n".join(L)
