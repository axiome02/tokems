from __future__ import annotations

from .engine.cards import est_carre, rang_du_carre
from .engine.state import GameState
from .i18n import t


def _indent(texte: str, prefixe: str = "        | ", vide: str = "(vide)") -> str:
    if not texte:
        return prefixe + vide
    return "\n".join(prefixe + ligne for ligne in texte.splitlines())


def rendre_debug(state: GameState, usage: dict | None = None) -> str:
    """Transcript ULTRA-DETAILLE pour l'observateur : mains, prompts, reponses brutes, tokens."""
    lang = state.config.lang
    L: list[str] = []
    L.append("#" * 72)
    L.append(t(lang, "debug_title"))
    L.append(t(lang, "debug_header", seed=state.config.master_seed, rangs=state.config.nb_rangs))
    for p in state.players:
        L.append(t(lang, "debug_player_line", pid=p.pid, nom=p.nom, equipe=p.equipe, modele=p.modele))
    L.append("#" * 72)

    # --- chats prives d'equipe (negociation) ---
    L.append(f"\n{t(lang, 'team_chats_title')}")
    for equipe in (0, 1):
        L.append(t(lang, "team_chat_header", equipe=equipe, signal=state.signals.get(equipe, "")))
        for ligne in state.team_channels.get(equipe, []):
            L.append(f"   {ligne}")

    # --- trace decision par decision ---
    L.append(f"\n{t(lang, 'detailed_run_title')}")
    tour_courant = None
    phase_courante = None
    for e in state.trace:
        if e["tour"] != tour_courant:
            tour_courant = e["tour"]
            phase_courante = None
            entete = (t(lang, "negotiation_header") if e["tour"] == 0
                      else t(lang, "manche_tour_header", manche=e.get("manche", 1), tour=e["tour"]))
            L.append(f"\n{'─' * 60}\n=== {entete} ===")
        if e["phase"] != phase_courante:
            phase_courante = e["phase"]
            L.append("\n" + t(lang, "phase_header", phase=phase_courante))

        carre = t(lang, "has_square_tag") if e["carre"] else ""
        L.append(f"\n  > {e['nom']} ({t(lang, 'team_word', equipe=e['equipe'])}){carre}")
        L.append(f"      {t(lang, 'hand_label')}{' '.join(e['main'])}")
        L.append(f"      {t(lang, 'center_label')}{' '.join(e['centre'])}")
        L.append(f"      {t(lang, 'action_label')}{e['action']}")
        if e["prompt_user"] is not None:
            L.append(f"      {t(lang, 'prompt_sent_label')}")
            L.append(_indent(e["prompt_user"], vide=t(lang, "empty_placeholder")))
            L.append(f"      {t(lang, 'raw_response_label')}")
            L.append(_indent(e["reponse_brute"] or "", vide=t(lang, "empty_placeholder")))

    # --- revelations ---
    L.append("\n" + "#" * 72)
    L.append(t(lang, "debug_revelations_title"))
    for p in state.players:
        h = state.hands[p.pid]
        carre = t(lang, "carre_note", rang=rang_du_carre(h)) if est_carre(h) else ""
        L.append(t(lang, "debug_final_hand", nom=p.nom, main=" ".join(str(c) for c in h), carre=carre))
    for o in state.historique_manches:
        w = o.get("winner_team")
        qui = t(lang, "draw_word") if w is None else t(lang, "team_word", equipe=w)
        L.append(t(lang, "debug_manche_line", manche=o.get("manche", "?"), qui=qui, reason=o.get("reason", "?")))
    if state.vainqueur_match is None:
        L.append(t(lang, "debug_final_score_draw", s0=state.scores[0], s1=state.scores[1]))
    else:
        L.append(t(lang, "debug_final_score_win", s0=state.scores[0], s1=state.scores[1],
                    equipe=state.vainqueur_match))

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
