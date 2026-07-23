from __future__ import annotations

import re
import unicodedata

# selecteurs de variante / jointures emoji : "☀️" et "☀" doivent etre le meme signe
_INVISIBLES = "️︎‍​"

# valeur posee par l'orchestrateur quand une equipe n'a convenu d'aucun signal
AUCUN_SIGNAL = "<aucun>"


def normaliser(texte: str) -> str:
    """Forme canonique d'un signal : minuscules, sans accents, sans ponctuation, espaces tasses.

    Les emojis sont conserves tels quels (seuls les selecteurs de variante sont retires).
    """
    s = unicodedata.normalize("NFKD", texte or "")
    s = "".join(c for c in s if not unicodedata.combining(c) and c not in _INVISIBLES)
    s = s.lower()
    # on garde lettres, chiffres et symboles (les emojis sont des symboles) ; toute
    # ponctuation devient un espace, y compris typographique (« » ’ …)
    s = "".join(c if unicodedata.category(c)[0] in "LNS" else " " for c in s)
    return re.sub(r"\s+", " ", s).strip()


def _contient(aiguille: str, botte: str) -> bool:
    """`aiguille` apparait dans `botte` en respectant les frontieres de mot."""
    if not aiguille:
        return False
    return re.search(rf"(?<!\w){re.escape(aiguille)}(?!\w)", botte) is not None


def _significatif(s: str) -> bool:
    """Evite qu'une reponse quelconque ('le', 'a') soit acceptee parce qu'elle est dans le signal."""
    return len(s) >= 3 or any(not c.isascii() for c in s)


def signal_trouve(signal: str, reponse: str) -> bool:
    """L'adversaire a-t-il demasque le signal ? Arbitrage deterministe (aucun LLM).

    Accepte dans les deux sens : le signal cite dans une phrase ("ils utilisent l'emoji ☀️"),
    ou une reponse nue qui est le coeur d'un signal verbeux ("tranquille" vs "le mot tranquille").
    """
    a, b = normaliser(signal), normaliser(reponse)
    # une equipe sans signal convenu ne peut pas etre "demasquee"
    if not a or not b or a == normaliser(AUCUN_SIGNAL):
        return False
    if _contient(a, b):
        return True
    return _significatif(b) and _contient(b, a)
