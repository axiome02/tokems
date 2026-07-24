from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Config:
    """Tous les boutons de reglage de la partie (voir CLAUDE.md, amelioration #1)."""

    nb_rangs: int = 10                 # cartes 1..nb_rangs (defaut 1-10 = 40 cartes, carres moins rapides)
    nb_joueurs: int = 4
    taille_main: int = 4
    taille_centre: int = 4

    # format : un MATCH est une suite de manches, chaque manche gagnee vaut 1 point
    points_pour_gagner: int = 3
    max_manches: int = 9               # borne de cout : au-dela, le match s'arrete au score

    # bornes de cout / duree (par manche)
    max_sous_tours_par_centre: int = 3
    max_centres_par_partie: int = 12
    max_tours: int = 8                 # ~5 tours sont necessaires entre l'emission et le KEMPS
    max_tours_negociation: int = 10    # echanges A<->B max par equipe pour convenir du signal
    tours_discussion: int = 2          # passes de parole par phase de discussion (chacun parle N fois)

    # combien des derniers evenements publics on envoie au LLM
    fenetre_chat: int = 40

    master_seed: int = 0
    # surcharges optionnelles : par defaut les deux flux sont derives du master_seed, mais on
    # peut les fixer separement (rejouer la meme donne avec un autre ordre de jeu, par exemple)
    seed_cards: int | None = None
    seed_order: int | None = None

    # langue de la partie : prompts LLM + evenements publics + transcript. "en" ou "fr".
    # Defaut "en" (norme des benchmarks publics) ; aucun recalibrage n'a ete fait pour "fr"
    # depuis l'introduction du multilingue (22/07/2026) : les mesures de reference restent en francais.
    lang: str = "en"

    # Optionnel : Evaluation semantique de la transmission du signal via LLM
    evaluer_signaux: bool = True      # si True, appelle un juge LLM pour evaluer la transmission
    modele_evaluateur: str | None = None  # specifie le modele/fournisseur du juge (ex: "gpt-4o")
