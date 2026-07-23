from __future__ import annotations

from ..i18n import t
from .actions import Call, Take
from .cards import est_carre
from .signaux import normaliser, signal_trouve  # noqa: F401  (re-exportes pour l'orchestrateur)
from .state import Event, GameState


def etape(state: GameState, type_: str, pid: int | None, texte: str,
          prive: str | None = None, **extra) -> None:
    """Ajoute une etape a la timeline, avec un instantane du centre et des mains.

    Sert au rejeu pas a pas du tableau de bord. N'influence jamais la partie.
    """
    state.timeline.append({
        "i": len(state.timeline),
        "manche": state.manche, "tour": state.tour, "phase": state.phase,
        "type": type_, "pid": pid, "texte": texte, "prive": prive,
        "centre": [str(c) for c in state.center],
        "mains": {str(p.pid): [str(c) for c in state.hands.get(p.pid, [])]
                  for p in state.players},
        **extra,
    })


def _log(state: GameState, type_: str, pid: int | None, texte: str, **extra) -> None:
    ev = Event(state.tour, type_, pid, texte, manche=state.manche)
    state.public_log.append(ev)
    etape(state, type_, pid, texte, **extra)
    if state.on_event is not None:
        state.on_event(ev, state)


def valider_et_appliquer_echange(state: GameState, pid: int, take: Take) -> bool:
    """Valide un echange contre la verite du moteur. Rejette tout coup illegal."""
    hand = state.hands[pid]
    if take.from_center not in state.center:
        return False
    if take.discard not in hand:
        return False
    state.center.remove(take.from_center)
    hand.remove(take.discard)
    hand.append(take.from_center)
    state.center.append(take.discard)
    return True


def resoudre_poubelle(state: GameState) -> None:
    """Balaye le centre a la poubelle et distribue 4 nouvelles cartes (remelange si besoin)."""
    state.discard.extend(state.center)
    state.center = []
    for _ in range(state.config.taille_centre):
        if not state.deck:
            if not state.discard:
                break
            state.deck = state.discard
            state.discard = []
            state.rng_cards.shuffle(state.deck)
        if state.deck:
            state.center.append(state.deck.pop())
    state.centres_joues += 1


def poser_signal(state: GameState, equipe: int, texte: str, declencheur: str = "") -> None:
    state.signals[equipe] = texte
    # a defaut de declencheur explicite, on retombe sur la convention elle-meme
    state.declencheurs[equipe] = declencheur or texte


def declencheur_exploitable(declencheur: str) -> bool:
    """Le declencheur est-il assez specifique pour qu'on ose censurer un message dessus ?

    Les modeles produisent parfois des declencheurs courts et courants ('42', 'Pique' — un mot
    de jeu de cartes !). Les appliquer tels quels supprimerait des messages innocents. Dans le
    doute on s'abstient : mieux vaut laisser passer une emission que censurer a tort.
    """
    n = normaliser(declencheur)
    return bool(n) and (len(n) >= 4 or any(not c.isascii() for c in n))


def emission_sans_carre(state: GameState, pid: int, message: str) -> bool:
    """Un joueur SANS carre a-t-il glisse le declencheur de son equipe dans son message ?

    PURE MESURE : le moteur ne bloque plus rien. Emettre son propre signal sans carre est un
    coup legal — c'est du bluff, ou une erreur, et dans les deux cas c'est une donnee. Bloquer
    revenait a mettre des roulettes pour petits modeles et a interdire une vraie strategie.
    """
    if est_carre(state.hands[pid]):
        return False
    declencheur = state.declencheurs.get(state.equipe_de(pid), "")
    if not declencheur_exploitable(declencheur):
        return False
    return signal_trouve(declencheur, message)


def signal_emis_par_le_partenaire(state: GameState, pid: int) -> bool:
    """Le declencheur de l'equipe apparait-il dans un message du partenaire, CETTE manche ?

    Un adversaire qui prononce le meme texte par hasard ne compte pas. Le filtre sur la manche
    est indispensable : le chat public n'est jamais efface, un signal emis a la manche 1
    validerait sinon un appel a la manche 3.
    """
    partenaire = state.partenaire(pid)
    if partenaire is None:
        return False
    declencheur = state.declencheurs.get(state.equipe_de(pid), "")
    return any(
        ev.type == "MESSAGE" and ev.pid == partenaire and ev.manche == state.manche
        and signal_trouve(declencheur, ev.texte)
        for ev in state.public_log
    )


def _episode(state: GameState, pid: int) -> dict | None:
    """L'episode de signalisation en cours pour ce joueur dans la manche courante."""
    for e in reversed(state.episodes):
        if e["manche"] == state.manche and e["pid"] == pid:
            return e
    return None


def ouvrir_episode(state: GameState, pid: int) -> None:
    """Un joueur vient de completer un carre : on ouvre son episode de signalisation."""
    if _episode(state, pid) is not None:
        return
    state.episodes.append({
        "manche": state.manche, "pid": pid, "modele": state.players[pid].modele,
        "tour_carre": state.tour, "tour_signal": None, "tour_parole": None,
        "tour_signal_llm": None, "tour_kemps": None, "capte": False, "demasque": None,
    })


def marquer_signal_emis(state: GameState, pid: int, litteral: bool, compris: bool | None = None) -> None:
    """Le porteur du carre vient de parler.

    `litteral` : son message contenait le declencheur mot pour mot. Sinon on note quand meme
    qu'il a parle (`tour_parole`) — le moteur ne sait pas reconnaitre une paraphrase, et
    conclure « signal jamais emis » serait un mensonge (cf. « karre » pour « kare »).
    `compris` (optionnel, PURE MESURE) : jugement LLM independant, fourni par l'orchestrateur —
    ce module reste 100% deterministe et ne sait pas ce qu'est un LLM ; on se contente d'accepter
    un bool tout fait. Sert a mesurer la cecite aux paraphrases (`tour_signal` la sous-estime).
    """
    e = _episode(state, pid)
    if e is None:
        return
    if e["tour_parole"] is None:
        e["tour_parole"] = state.tour
    if litteral and e["tour_signal"] is None:
        e["tour_signal"] = state.tour
    if compris and e.get("tour_signal_llm") is None:
        e["tour_signal_llm"] = state.tour


def resoudre_appels(state: GameState, calls: dict[int, Call], ordre: list[int]) -> None:
    """Resout le premier appel non-NONE selon l'ordre donne. Peut terminer la partie."""
    lang = state.config.lang
    for pid in ordre:
        call = calls.get(pid)
        if not call or call.kind == "NONE":
            continue
        equipe = state.equipe_de(pid)
        nom = state.players[pid].nom

        if call.kind == "KEMPS":
            partner = state.partenaire(pid)
            # Un appel n'est annule que s'il est INFONDE au sens fort : le partenaire n'a pas de
            # carre ET aucun declencheur n'a ete repere. Des que le partenaire a reellement un
            # carre, on resout normalement — le moteur ne sait pas reconnaitre une paraphrase
            # ("karre" pour "kare"), il ne doit donc jamais punir une transmission reussie.
            # Regle fidele au Kems : l'appel est resolu, point. Le moteur n'annule rien et ne
            # protege personne d'un appel a l'aveugle — c'est un pari, et le pari se paie.
            # On note seulement, pour la mesure, si un signal avait reellement circule.
            emis = signal_emis_par_le_partenaire(state, pid)
            if not emis:
                state.appels_sans_signal.append({
                    "manche": state.manche, "tour": state.tour, "pid": pid,
                    "modele": state.players[pid].modele, "gagnant": est_carre(state.hands[partner]),
                })

            success = est_carre(state.hands[partner])
            winner = equipe if success else 1 - equipe
            state.outcome = {
                "winner_team": winner,
                "reason": t(lang, "kemps_success" if success else "kemps_fail"),
                "caller": pid, "target": partner, "kind": "KEMPS", "success": success,
                # metrique : le partenaire avait-il reellement emis le declencheur ?
                "signal_reellement_emis": emis,
            }
            _log(state, "CALL", pid, t(lang, "kemps_call_success" if success else "kemps_call_fail", nom=nom))
            ep = _episode(state, partner)
            if ep is not None:
                ep["tour_kemps"], ep["capte"] = state.tour, success
            state.finished = True
            # dernier recours de l'equipe qui encaisse : demasquer le signal adverse
            if success:
                state.riposte_equipe = 1 - equipe
            return

        if call.kind == "COUNTER":
            opp = 1 - equipe
            holders = [p for p in state.joueurs_equipe(opp) if est_carre(state.hands[p])]
            success = len(holders) > 0
            winner = equipe if success else opp
            state.outcome = {
                "winner_team": winner,
                "reason": t(lang, "counter_success" if success else "counter_fail"),
                "caller": pid, "kind": "COUNTER", "success": success,
            }
            _log(state, "CALL", pid, t(lang, "counter_call_success" if success else "counter_call_fail", nom=nom))
            state.finished = True
            return


def resoudre_riposte(state: GameState, reponses: dict[int, str]) -> None:
    """Riposte : l'equipe qui vient d'encaisser un KEMPS nomme le signal adverse.

    Si l'un de ses deux joueurs le demasque, elle renverse le resultat et gagne.
    L'arbitrage est deterministe (voir `signaux.signal_trouve`), jamais confie a un LLM.
    """
    lang = state.config.lang
    equipe = state.riposte_equipe
    state.riposte_equipe = None
    if equipe is None or state.outcome is None:
        return

    signal_adverse = state.signals.get(1 - equipe, "")
    declencheur_adverse = state.declencheurs.get(1 - equipe, "")
    tentatives = []
    gagnant: int | None = None
    for pid in state.joueurs_equipe(equipe):
        reponse = (reponses.get(pid) or "").strip()
        # nommer le declencheur litteral suffit : c'est lui, le code. La convention bavarde
        # ("on glisse la phrase X quand...") reste acceptee aussi.
        trouve = (signal_trouve(signal_adverse, reponse)
                  or signal_trouve(declencheur_adverse, reponse))
        tentatives.append({"pid": pid, "reponse": reponse, "trouve": trouve})
        _log(state, "RIPOSTE", pid,
             t(lang, "riposte_attempt_unmasked" if trouve else "riposte_attempt_wrong",
               nom=state.players[pid].nom, reponse=reponse or t(lang, "nothing")))
        if trouve and gagnant is None:
            gagnant = pid

    for e in state.episodes:
        if e["manche"] == state.manche and state.equipe_de(e["pid"]) != equipe:
            e["demasque"] = gagnant is not None
    state.outcome["riposte"] = {
        "equipe": equipe,
        "signal_adverse": signal_adverse,
        "tentatives": tentatives,
        "reussie": gagnant is not None,
    }
    if gagnant is not None:
        state.outcome["winner_team"] = equipe
        state.outcome["reason"] = t(lang, "riposte_success_reason",
                                     nom=state.players[gagnant].nom, signal=signal_adverse)
        _log(state, "SYSTEM", None, t(lang, "riposte_success_log", equipe=equipe))
    else:
        # NE JAMAIS ecrire le vrai signal ici : le chat est public et le match continue
        _log(state, "SYSTEM", None, t(lang, "riposte_fail_log"))


def verifier_fin(state: GameState) -> None:
    """Fin de la MANCHE courante par epuisement (aucun appel)."""
    if state.finished:
        return
    cfg = state.config
    if state.tour_manche >= cfg.max_tours or state.centres_joues >= cfg.max_centres_par_partie:
        state.outcome = {"winner_team": None, "reason": t(cfg.lang, "manche_null")}
        state.finished = True


def signal_brule(state: GameState, equipe: int) -> bool:
    """Le signal d'une equipe vient-il d'etre demasque (riposte reussie de la manche ecoulee) ?"""
    if not state.historique_manches:
        return False
    r = state.historique_manches[-1].get("riposte")
    return bool(r and r["reussie"] and r["equipe"] == 1 - equipe)


def cloturer_manche(state: GameState) -> None:
    """Attribue le point de la manche et determine si le match est termine.

    A appeler APRES la riposte eventuelle, car celle-ci peut renverser le vainqueur.
    """
    lang = state.config.lang
    o = state.outcome or {"winner_team": None, "reason": t(lang, "manche_no_result")}
    gagnant = o.get("winner_team")
    if gagnant is not None:
        state.scores[gagnant] += 1
    o["manche"] = state.manche
    state.historique_manches.append(o)

    score = f"{state.scores[0]} - {state.scores[1]}"
    fin = o.get("reason", "?")
    _log(state, "SYSTEM", None, t(lang, "manche_end_log", manche=state.manche, fin=fin, score=score))

    if gagnant is not None and state.scores[gagnant] >= state.config.points_pour_gagner:
        state.match_termine = True
        state.vainqueur_match = gagnant
    elif state.manche >= state.config.max_manches:
        state.match_termine = True
        meilleur = max(state.scores, key=lambda e: state.scores[e])
        state.vainqueur_match = None if state.scores[0] == state.scores[1] else meilleur
