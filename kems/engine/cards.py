from __future__ import annotations

from dataclasses import dataclass

COULEURS = ["♠", "♥", "♦", "♣"]  # pique, coeur, carreau, trefle


@dataclass(frozen=True)
class Card:
    rang: int          # 1..nb_rangs
    couleur: str       # un des COULEURS

    def __str__(self) -> str:
        return f"{self.rang}{self.couleur}"


def construire_paquet(nb_rangs: int) -> list[Card]:
    return [Card(r, c) for r in range(1, nb_rangs + 1) for c in COULEURS]


def est_carre(main: list[Card]) -> bool:
    """Vrai si la main est un carre : 4 cartes du meme rang."""
    return len(main) == 4 and len({c.rang for c in main}) == 1


def rang_du_carre(main: list[Card]) -> int | None:
    return main[0].rang if est_carre(main) else None
