from __future__ import annotations

from dataclasses import dataclass, field

from .cards import Card, est_carre
from .state import Event, GameState


@dataclass
class PlayerView:
    """Ce qu'un joueur a le DROIT de voir. Frontiere de securite : aucune info privee d'autrui."""

    pid: int
    nom: str
    equipe: int
    nom_partenaire: str

    ma_main: list[Card]
    jai_un_carre: bool                   # dit par l'arbitre (anti-hallucination)
    mon_signal: str
    mon_declencheur: str                 # le texte LITTERAL epingle par le moteur (anti-confabulation)
    mon_plan: str
    mon_chat_equipe: list[str]
    mon_journal: list[str]               # monologue interieur, invisible de TOUS les autres

    centre: list[Card]                   # public
    chat_global: list[Event]             # fenetre bornee du chat public

    scores: dict[int, int] = field(default_factory=dict)   # score du match
    manche: int = 1                                        # numero de la manche courante
    historique_manches: list[dict] = field(default_factory=list)  # historique des manches ecoulees

    nego_proposition: str = ""           # negociation : le signal candidat en cours de discussion
    nego_declencheur: str = ""           # negociation : le declencheur sur la table (a re-ecrire pour sceller)
    nego_restants: int = 0               # negociation : echanges restants avant le figeage au plafond
    ma_reflexion: str = ""               # la reflexion privee que le joueur vient tout juste d'ecrire
    adversaires: list[str] = field(default_factory=list)   # public : noms de l'equipe adverse


def vue_pour(state: GameState, pid: int,
             nego_proposition: str = "", chat_complet: bool = False,
             reflexion: str = "", nego_declencheur: str = "",
             nego_restants: int = 0) -> PlayerView:
    e = state.equipe_de(pid)
    fen = len(state.public_log) if chat_complet else state.config.fenetre_chat
    return PlayerView(
        pid=pid,
        nom=state.players[pid].nom,
        equipe=e,
        nom_partenaire=state.players[state.partenaire(pid)].nom if state.partenaire(pid) is not None else "?",
        ma_main=list(state.hands[pid]),
        jai_un_carre=est_carre(state.hands[pid]),
        mon_signal=state.signals.get(e, ""),
        mon_declencheur=state.declencheurs.get(e, ""),
        mon_plan=state.plans.get(pid, ""),
        mon_chat_equipe=list(state.team_channels.get(e, [])),
        mon_journal=list(state.journaux.get(pid, [])),
        centre=list(state.center),
        chat_global=list(state.public_log[-fen:]),
        scores=dict(state.scores),
        manche=state.manche,
        historique_manches=list(state.historique_manches),
        nego_proposition=nego_proposition,
        nego_declencheur=nego_declencheur,
        nego_restants=nego_restants,
        ma_reflexion=reflexion,
        adversaires=[p.nom for p in state.players if p.equipe != e],
    )
