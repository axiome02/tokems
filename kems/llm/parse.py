from __future__ import annotations

import re

from ..engine.actions import Call, Guess, Nego, Pass, Take
from ..engine.views import PlayerView


def _ligne(texte: str, label: str) -> str | None:
    """Valeur d'un champ 'LABEL: valeur'.

    La valeur doit etre sur la MEME ligne que le label : avec `\\s*`, un label suivi d'un
    retour a la ligne capturait la ligne d'apres (un 'PROPOSITION:' vide a deja fait epingler
    '- Conventions:' comme signal secret pendant toute une partie).
    """
    m = re.search(rf"{re.escape(label)}[ \t]*:[ \t]*(\S.*)", texte, re.IGNORECASE)
    return m.group(1).strip() if m else None


def _nettoyer(msg: str) -> str:
    """Retire les artefacts markdown/guillemets qui entourent un message LLM.

    Retire aussi les DIDASCALIES : les modeles annotent leur propre message avec leur
    intention — « C'est la saison ! » *(en utilisant le signal secret convenu)*. Publier ca
    revient a publier leurs aveux : en partie 707 les adversaires n'ont pas deduit le code,
    ils l'ont simplement lu. On coupe donc tout ce qui suit un '*(' — une sequence qu'aucune
    phrase normale ne contient, contrairement a une parenthese isolee qu'on laisse tranquille.
    """
    s = re.sub(r"\*+\s*\(.*", "", msg, flags=re.DOTALL)
    s = s.strip()
    s = re.sub(r'^[\*_"“”«»\s]+', "", s)
    s = re.sub(r'[\*_"“”«»\s]+$', "", s)
    return s


def _trouver_carte(token: str, pool):
    for c in pool:
        if str(c) == token:
            return c
    return None


def parse_carte(texte: str, view: PlayerView):
    """'ACTION: TAKE 7♦ DISCARD 3♠' -> Take, sinon Pass (repli robuste)."""
    m = re.search(r"TAKE\s+(\S+)\s+DISCARD\s+(\S+)", texte, re.IGNORECASE)
    if m:
        fc = _trouver_carte(m.group(1), view.centre)
        dc = _trouver_carte(m.group(2), view.ma_main)
        if fc is not None and dc is not None:
            return Take(from_center=fc, discard=dc)
    return Pass()


def parse_negociation(texte: str) -> Nego:
    """Un tour de negociation -> Nego(message, proposition, declencheur, accord).

    accord=True signifie que le joueur VERROUILLE la proposition sur la table.
    Chaque champ accepte son label FR et son label EN (le prompt envoye au modele n'utilise
    qu'un seul vocabulaire a la fois selon `lang`, mais le parsing reste independant de la
    langue effective — robuste si un modele repond dans l'autre langue par derive).
    'PROPOSITION'/'PROPOSAL' est le nom canonique ; 'SIGNAL_CONVENU' est accepte comme alias.
    'DECLENCHEUR'/'TRIGGER' est le texte litteral que le moteur devra savoir reperer.
    """
    msg = _nettoyer(_ligne(texte, "MESSAGE") or "")
    prop = _ligne(texte, "PROPOSITION") or _ligne(texte, "PROPOSAL") or _ligne(texte, "SIGNAL_CONVENU")
    decl = _ligne(texte, "DECLENCHEUR") or _ligne(texte, "TRIGGER")
    accord_brut = (_ligne(texte, "ACCORD") or _ligne(texte, "AGREE") or "").strip().upper()
    accord = accord_brut.startswith("O") or accord_brut.startswith("Y")  # OUI / YES
    return Nego(
        message=msg,
        proposition=_nettoyer(prop) if prop else None,
        declencheur=_nettoyer(decl) if decl else None,
        accord=accord,
    )


def parse_discussion(texte: str, view: PlayerView) -> tuple[str, Call, str]:
    msg = _nettoyer(_ligne(texte, "MESSAGE") or "")
    call_raw = (_ligne(texte, "CALL") or "NONE").upper()
    kind = "KEMPS" if "KEMPS" in call_raw else ("COUNTER" if "COUNTER" in call_raw else "NONE")

    plan = _ligne(texte, "PLAN") or view.mon_plan
    return msg, Call(kind), plan


def parse_riposte(texte: str) -> Guess:
    """'SIGNAL_ADVERSE: ☀️' (ou 'OPPONENT_SIGNAL:') -> Guess. Repli : la derniere ligne non vide."""
    brut = (_ligne(texte, "SIGNAL_ADVERSE") or _ligne(texte, "OPPONENT_SIGNAL")
            or _ligne(texte, "SIGNAL"))
    if brut is None:
        lignes = [l for l in (texte or "").splitlines() if l.strip()]
        brut = lignes[-1] if lignes else ""
    return Guess(reponse=_nettoyer(brut))


def parse_jugement(texte: str) -> bool:
    """'SIGNAL: YES'/'OUI' -> True. Jugement LLM de mesure ; n'intervient jamais dans la resolution."""
    brut = (_ligne(texte, "SIGNAL") or "").strip().upper()
    return brut.startswith("Y") or brut.startswith("O")
