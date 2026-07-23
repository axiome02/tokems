from __future__ import annotations

from dataclasses import dataclass, field
from random import Random
from typing import Callable

from ..config import Config
from .cards import Card


@dataclass
class Player:
    pid: int
    nom: str
    equipe: int
    modele: str


@dataclass
class Event:
    """Une ligne du chat global PUBLIC (coup, message, appel, systeme)."""

    tour: int
    type: str            # SWAP | PASS | MESSAGE | CALL | SWEEP | RIPOSTE | SYSTEM
    pid: int | None
    texte: str
    manche: int = 1


@dataclass
class GameState:
    config: Config
    players: list[Player]

    hands: dict[int, list[Card]]          # PRIVE : pid -> main
    center: list[Card]                    # public
    deck: list[Card]
    discard: list[Card]

    signals: dict[int, str] = field(default_factory=dict)          # PRIVE equipe : equipe -> signal
    declencheurs: dict[int, str] = field(default_factory=dict)     # PRIVE equipe : texte litteral a reperer
    nego_convergence: dict[int, bool] = field(default_factory=dict)  # MESURE : accord scelle (True) ou fige au plafond (False)
    plans: dict[int, str] = field(default_factory=dict)            # PRIVE joueur : pid -> plan
    journaux: dict[int, list[str]] = field(default_factory=dict)   # PRIVE joueur : son monologue interieur
    team_channels: dict[int, list[str]] = field(default_factory=dict)  # PRIVE equipe
    public_log: list[Event] = field(default_factory=list)         # LE chat global

    phase: str = "SETUP"
    tour: int = 0                     # numero de tour GLOBAL, croissant sur tout le match
    tour_manche: int = 0              # numero de tour dans la manche courante (bornes de cout)
    centres_joues: int = 0

    # --- match : suite de manches, 1 point par manche gagnee ---
    manche: int = 1
    scores: dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0})
    match_termine: bool = False
    vainqueur_match: int | None = None
    historique_manches: list[dict] = field(default_factory=list)   # outcome de chaque manche

    # suite ORDONNEE de toutes les etapes (publiques ET privees), avec l'etat du centre et des
    # mains a chaque instant. FLUX D'OBSERVABILITE UNIQUE : le tableau de bord la rejoue pas a
    # pas (sans les champs lourds), le transcript debug filtre les etapes portant une decision
    # (`action` present, avec prompt et reponse brute du LLM).
    timeline: list[dict] = field(default_factory=list)

    # --- mesures du livrable ---
    # un episode par carre forme : carre -> signal emis -> capte ? -> demasque ?
    episodes: list[dict] = field(default_factory=list)
    # appels lances alors qu'aucun signal n'avait circule (pari a l'aveugle : gagnant ou non)
    appels_sans_signal: list[dict] = field(default_factory=list)
    # messages ou un joueur a emis son propre code SANS carre (bluff ou erreur) — pure mesure
    emissions_sans_carre: list[dict] = field(default_factory=list)
    # combien de messages publics chaque joueur avait vus lors de sa derniere reflexion
    vu_a_la_reflexion: dict[int, int] = field(default_factory=dict)

    rng_cards: Random | None = None
    rng_order: Random | None = None

    finished: bool = False
    outcome: dict | None = None

    # equipe qui vient d'encaisser un KEMPS reussi et a droit a une riposte (None = pas de riposte)
    riposte_equipe: int | None = None

    # callback optionnel appele a chaque evenement public (pour l'affichage --live)
    on_event: Callable | None = None

    # --- helpers ---
    def equipe_de(self, pid: int) -> int:
        return self.players[pid].equipe

    def partenaire(self, pid: int) -> int | None:
        e = self.players[pid].equipe
        for p in self.players:
            if p.equipe == e and p.pid != pid:
                return p.pid
        return None

    def joueurs_equipe(self, equipe: int) -> list[int]:
        return [p.pid for p in self.players if p.equipe == equipe]
