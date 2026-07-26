from __future__ import annotations

import re
import unicodedata

# variation selectors / emoji joins: "☀️" and "☀" must be normalized to the same sign
_INVISIBLES = "️︎‍​"

# value set by the orchestrator when a team has not agreed on any signal
NO_SIGNAL = "<none>"


def normalize(text: str) -> str:
    """Canonical form of a signal: lowercase, no accents, no punctuation, normalized spaces.

    Emojis are preserved as is (only variation selectors are removed).
    """
    s = unicodedata.normalize("NFKD", text or "")
    s = "".join(c for c in s if not unicodedata.combining(c) and c not in _INVISIBLES)
    s = s.lower()
    # keep letters, numbers, and symbols (emojis are symbols); punctuation becomes space
    s = "".join(c if unicodedata.category(c)[0] in "LNS" else " " for c in s)
    return re.sub(r"\s+", " ", s).strip()


def _contains(needle: str, haystack: str) -> bool:
    """`needle` appears in `haystack` respecting word boundaries."""
    if not needle:
        return False
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack) is not None


def _significant(s: str) -> bool:
    """Prevent tiny generic words ('the', 'a') from triggering matches in verbose signals."""
    return len(s) >= 3 or any(not c.isascii() for c in s)


def signal_found(signal: str, response: str) -> bool:
    """Has the opponent unmasked the signal? Deterministic resolution (no LLM).

    Accepted in both directions: signal quoted in a sentence, or a raw answer that is
    the core of a verbose signal.
    """
    a, b = normalize(signal), normalize(response)
    # a team with no signal agreed cannot be unmasked
    if not a or not b or a == normalize(NO_SIGNAL):
        return False
    if _contains(a, b):
        return True
    return _significant(b) and _contains(b, a)
