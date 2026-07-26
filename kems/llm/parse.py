from __future__ import annotations

import re

from ..engine.actions import Call, Guess, Nego, Pass, Take
from ..engine.views import PlayerView


def _line(text: str, label: str) -> str | None:
    """Value of a field 'LABEL: value'.

    The value must be on the SAME line as the label: with `\\s*`, a label followed by a
    newline was capturing the next line.
    """
    m = re.search(rf"{re.escape(label)}[ \t]*:[ \t]*(\S.*)", text, re.IGNORECASE)
    return m.group(1).strip() if m else None


def _clean(msg: str) -> str:
    """Removes markdown artifacts/quotes surrounding an LLM message.

    Also removes stage directions (didascalies): models annotate their own message with their
    intention - "It's the season!" *(using the agreed secret signal)*. Publishing this
    amounts to publishing their confession. We cut everything following a '*(' - a sequence
    no normal sentence contains.
    """
    s = re.sub(r"\*+\s*\(.*", "", msg, flags=re.DOTALL)
    s = s.strip()
    s = re.sub(r'^[\*_"“”«»\s]+', "", s)
    s = re.sub(r'[\*_"“”«»\s]+$', "", s)
    return s


def _find_card(token: str, pool):
    for c in pool:
        if str(c) == token:
            return c
    return None


def parse_card(text: str, view: PlayerView):
    """'ACTION: TAKE 7♦ DISCARD 3♠' -> Take, else Pass (robust fallback)."""
    m = re.search(r"TAKE\s+(\S+)\s+DISCARD\s+(\S+)", text, re.IGNORECASE)
    if m:
        fc = _find_card(m.group(1), view.center)
        dc = _find_card(m.group(2), view.my_hand)
        if fc is not None and dc is not None:
            return Take(from_center=fc, discard=dc)
    return Pass()


def parse_negotiation(text: str) -> Nego:
    """A negotiation turn -> Nego(message, proposition, trigger, agree, plan).

    agree=True means the player locks the proposal on the table.
    Each field accepts its FR and EN label (prompts sent use only one vocabulary at a time
    based on `lang`, but parsing remains language-independent for robustness).
    'PROPOSITION'/'PROPOSAL' is the canonical name; 'SIGNAL_CONVENU' is accepted as an alias.
    'DECLENCHEUR'/'TRIGGER' is the literal text the engine will have to detect.
    """
    msg = _clean(_line(text, "MESSAGE") or "")
    prop = _line(text, "PROPOSITION") or _line(text, "PROPOSAL") or _line(text, "SIGNAL_CONVENU")
    decl = _line(text, "DECLENCHEUR") or _line(text, "TRIGGER")
    agree_raw = (_line(text, "ACCORD") or _line(text, "AGREE") or "").strip().upper()
    agree = agree_raw.startswith("O") or agree_raw.startswith("Y")  # OUI / YES
    plan = _line(text, "PLAN")
    return Nego(
        message=msg,
        proposition=_clean(prop) if prop else None,
        trigger=_clean(decl) if decl else None,
        agree=agree,
        plan=plan.strip() if plan else None,
    )


def parse_discussion(text: str, view: PlayerView) -> tuple[str, Call, str]:
    msg = _clean(_line(text, "MESSAGE") or "")
    call_raw = (_line(text, "CALL") or "NONE").upper()
    kind = "KEMPS" if "KEMPS" in call_raw else ("COUNTER" if "COUNTER" in call_raw else "NONE")

    plan = _line(text, "PLAN") or view.my_plan
    return msg, Call(kind), plan


def parse_riposte(text: str) -> Guess:
    """'SIGNAL_ADVERSE: ☀️' (or 'OPPONENT_SIGNAL:') -> Guess. Fallback: the last non-empty line."""
    brut = (_line(text, "SIGNAL_ADVERSE") or _line(text, "OPPONENT_SIGNAL")
            or _line(text, "SIGNAL"))
    if brut is None:
        lines = [l for l in (text or "").splitlines() if l.strip()]
        brut = lines[-1] if lines else ""
    return Guess(response=_clean(brut))


def parse_judgment(text: str) -> bool:
    """'SIGNAL: YES'/'OUI' -> True. LLM Judge measurement; never affects game resolution."""
    brut = (_line(text, "SIGNAL") or "").strip().upper()
    return brut.startswith("Y") or brut.startswith("O")
