from __future__ import annotations

from dataclasses import dataclass

from .cards import Card


@dataclass
class Take:
    """Echange 1-pour-1 : prendre `from_center` au centre, reposer `discard` de sa main."""

    from_center: Card
    discard: Card


@dataclass
class Pass:
    """Ne rien prendre ce sous-tour."""


@dataclass
class Call:
    kind: str  # "KEMPS" | "COUNTER" | "NONE"


@dataclass
class Nego:
    """Un tour de negociation : ce que le joueur dit, propose, et le declencheur exact retenu."""

    message: str
    proposition: str | None
    declencheur: str | None      # le texte litteral que le moteur devra savoir reperer
    accord: bool
    plan: str | None = None      # plan personnel / memoire (optionnel)


@dataclass
class Guess:
    """Riposte : la reponse d'un joueur quand on lui demande le signal secret adverse."""

    reponse: str
