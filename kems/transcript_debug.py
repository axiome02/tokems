from __future__ import annotations

from .engine.cards import is_square, square_rank
from .engine.state import GameState
from .i18n import t


def _indent(text: str, prefix: str = "        | ", empty: str = "(empty)") -> str:
    if not text:
        return prefix + empty
    return "\n".join(prefix + line for line in text.splitlines())


def rendre_debug(state: GameState, usage: dict | None = None) -> str:
    """ULTRA-DETAILED transcript for the observer: hands, prompts, raw responses, tokens."""
    lang = state.config.lang
    L: list[str] = []
    L.append("#" * 72)
    L.append(t(lang, "debug_title"))
    L.append(t(lang, "debug_header", seed=state.config.master_seed, rangs=state.config.num_ranks))
    for p in state.players:
        L.append(t(lang, "debug_player_line", pid=p.pid, nom=p.name, equipe=p.team, modele=p.model))
    L.append("#" * 72)

    # --- private team chats (negotiation) ---
    L.append(f"\n{t(lang, 'team_chats_title')}")
    for team in (0, 1):
        L.append(t(lang, "team_chat_header", equipe=team, signal=state.signals.get(team, "")))
        for line in state.team_channels.get(team, []):
            L.append(f"   {line}")

    # --- decision by decision: timeline steps carrying an action ---
    L.append(f"\n{t(lang, 'detailed_run_title')}")
    tour_courant = None
    phase_courante = None
    for e in state.timeline:
        if "action" not in e:
            continue
        if e["turn"] != tour_courant:
            tour_courant = e["turn"]
            phase_courante = None
            entete = (t(lang, "negotiation_header") if e["turn"] == 0
                      else t(lang, "manche_tour_header", manche=e.get("round", 1), tour=e["turn"]))
            L.append(f"\n{'─' * 60}\n=== {entete} ===")
        # same granularity as old trace: SWAP/PASS -> EXCHANGE, MESSAGE -> DISCUSSION
        phase = {"SWAP": "EXCHANGE", "PASS": "EXCHANGE", "SYSTEM": "EXCHANGE",
                 "MESSAGE": "DISCUSSION"}.get(e["type"], e["type"])
        if phase != phase_courante:
            phase_courante = phase
            L.append("\n" + t(lang, "phase_header", phase=phase_courante))

        joueur = state.players[e["pid"]]
        carre = t(lang, "has_square_tag") if e["carre"] else ""
        L.append(f"\n  > {joueur.name} ({t(lang, 'team_word', equipe=joueur.team)}){carre}")
        L.append(f"      {t(lang, 'hand_label')}{' '.join(e['main'])}")
        L.append(f"      {t(lang, 'center_label')}{' '.join(e['center'])}")
        L.append(f"      {t(lang, 'action_label')}{e['action']}")
        if e["prompt_user"] is not None:
            L.append(f"      {t(lang, 'prompt_sent_label')}")
            L.append(_indent(e["prompt_user"], empty=t(lang, "empty_placeholder")))
            L.append(f"      {t(lang, 'raw_response_label')}")
            L.append(_indent(e["reponse_brute"] or "", empty=t(lang, "empty_placeholder")))

    # --- revelations ---
    L.append("\n" + "#" * 72)
    L.append(t(lang, "debug_revelations_title"))
    for p in state.players:
        h = state.hands[p.pid]
        carre = t(lang, "carre_note", rang=square_rank(h)) if is_square(h) else ""
        L.append(t(lang, "debug_final_hand", nom=p.name, main=" ".join(str(c) for c in h), carre=carre))
    for o in state.round_history:
        w = o.get("winner_team")
        qui = t(lang, "draw_word") if w is None else t(lang, "team_word", equipe=w)
        L.append(t(lang, "debug_manche_line", manche=o.get("round", "?"), qui=qui, reason=o.get("reason", "?")))
    if state.match_winner is None:
        L.append(t(lang, "debug_final_score_draw", s0=state.scores[0], s1=state.scores[1]))
    else:
        L.append(t(lang, "debug_final_score_win", s0=state.scores[0], s1=state.scores[1],
                    equipe=state.match_winner))

    # --- tokens ---
    if usage is not None:
        L.append(f"\n{t(lang, 'token_usage_title')}")
        per_model, grand = usage["per_model"], usage["grand_total"]
        for nom, d in per_model.items():
            L.append(f"  {nom:10s} : {d['calls']:4d} appels | "
                      f"prompt {d['prompt']:6d} + completion {d['completion']:6d} = {d['total']:6d} tokens")
        L.append(f"  {'TOTAL':10s} : {grand} tokens")
    L.append("#" * 72)
    return "\n".join(L)
