from __future__ import annotations

from ..engine.views import PlayerView

# Principle: give the FACTS (what the engine knows) and the CONSTRAINTS (the rules),
# never the shape of what to invent nor the content of what to write.

# short version, for micro card decisions (token economy)
REGLES_CARTE = (
    "In Kems, your goal is to hold 4 cards of the SAME RANK in your hand (a 'square', e.g. 7♠7♥7♦7♣). "
    "Only the RANK (the number) matters ; SUITS have NO importance whatsoever."
)

# short reminder shared by the macro prompts
RAPPEL = (
    "Kems, 2 vs 2. Goal: hold 4 cards of the SAME RANK (a square ; suit doesn't matter). "
    "You and your teammate have agreed on a secret message. Whoever has a square slips it "
    "into the public chat, the other then calls KEMPS and you win. Calling KEMPS when your "
    "teammate does not have a square loses the round. "
    "Both opponents read the whole chat: if they understand your secret message, they win."
)


def _fmt_cards(cards) -> str:
    return " ".join(str(c) for c in cards) if cards else "(empty)"


def _fmt_chat_messages(events, limite: int = 8) -> str:
    """Keeps only the recent conversation (messages + calls), not the exchange noise."""
    conv = [ev for ev in events if ev.type in ("MESSAGE", "CALL")]
    conv = conv[-limite:]
    if not conv:
        return "(no messages yet)"
    return "\n".join(ev.texte for ev in conv)


# ─────────────────────────── micro: card decision ───────────────────────────
def prompt_micro_carte(view: PlayerView) -> tuple[str, str]:
    system = (
        REGLES_CARTE + "\n"
        "It's your turn to exchange: take ONE card from the center while discarding ONE of your "
        "own, or pass. Reply ONLY with an 'ACTION: ...' line."
    )
    user = (
        f"YOUR HAND: {_fmt_cards(view.ma_main)}\n"
        f"CENTER: {_fmt_cards(view.centre)}\n"
        f"YOUR PLAN: {view.mon_plan or '(none)'}\n"
        "'ACTION: TAKE <card_from_center> DISCARD <card_from_your_hand>' or 'ACTION: PASS'."
    )
    return system, user


# ─────────────────────────── macro: signal negotiation ───────────────────────
def prompt_negociation(view: PlayerView) -> tuple[str, str]:
    system = (
        RAPPEL + "\n\n"
        "The game hasn't started yet. You're talking privately with your teammate to agree on a "
        "SECRET MESSAGE: a way to let them know, later and in the middle of the public chat, that "
        "you have a square. Both your opponents will read that chat. So your teammate must "
        "understand it without fail, and the other two must suspect nothing: if they understand "
        "it, you lose. Anything goes on FORM, it's up to you to invent it. But your convention "
        "must meet three conditions, otherwise it will be useless:\n"
        "1. DECIDABLE — reading a message, each of you must be able to answer YES or NO without "
        "hesitating: is this the signal, yes or no? A convention that requires interpreting a tone, "
        "an intention, or 'a particular turn of phrase' is unusable: you won't be able to agree.\n"
        "2. IN A SINGLE STEP — whoever has the square sends it, the other calls KEMPS right away. "
        "Don't invent a protocol where one waits for a reply or confirmation from the other: "
        "neither of you will ever dare go first, and you'll both stay stuck.\n"
        "3. INVISIBLE IN HINDSIGHT — the opponents can call COUNTER during play the moment they "
        "suspect a square, and if your KEMPS succeeds they get one last chance: each of them "
        "re-reads the ENTIRE public chat and must name your secret message — a single correct "
        "answer turns your win into theirs. A trigger that sticks out of ordinary table talk "
        "therefore loses even when it works: your teammate must recognize it instantly, yet "
        "someone combing through the log afterwards must find nothing that looks like a code.\n"
        "Discuss for real: propose, object, look for the flaws. "
        "Only lock it in once you're both convinced you can recognize it."
    )
    dialogue = "\n".join(view.mon_chat_equipe) if view.mon_chat_equipe else "(you're opening the discussion)"
    user = (
        "━━ YOUR PRIVATE DISCUSSION ━━\n"
        f"{dialogue}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"PROPOSAL ON THE TABLE: {view.nego_proposition or '(none)'}\n\n"
        "Reply on these lines:\n"
        "MESSAGE: <what you say to your teammate>\n"
        "PROPOSAL: <the convention you're proposing ; copy the one on the table if you're keeping it>\n"
        "TRIGGER: <the exact text to spot, just a few words, no explanation>\n"
        "AGREE: YES only if you're definitively locking in your teammate's proposal, otherwise NO"
    )
    return system, user


# ─────────────────────────── macro: private reflection (before speaking) ───────────
def prompt_reflexion(view: PlayerView) -> tuple[str, str]:
    """Inner monologue: nobody reads it, no imposed format, no suggested conclusion."""
    system = (
        RAPPEL + "\n\n"
        "You're taking a moment to think before speaking in public. What you write here is "
        "strictly for yourself: neither your teammate nor your opponents will ever read it. "
        "Keep it short: 3 lines max, no headings, no lists, no detailed action plan. "
        "Get straight to what matters right now."
    )
    journal = "\n".join(f"- {l}" for l in view.mon_journal[-2:]) or "(nothing yet)"
    user = (
        "━━ OFFICIAL FACTS ━━\n"
        f"YOU ARE: {view.nom}  |  YOUR TEAMMATE: {view.nom_partenaire}\n"
        f"YOUR HAND: {_fmt_cards(view.ma_main)}  |  DO YOU HAVE A SQUARE: {'YES' if view.jai_un_carre else 'NO'}\n"
        f"YOUR AGREED SECRET MESSAGE: {view.mon_signal}\n"
        "━━ RECENT PUBLIC MESSAGES ━━\n"
        f"{_fmt_chat_messages(view.chat_global)}\n"
        "━━ YOUR PREVIOUS THOUGHTS ━━\n"
        f"{journal}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "What's on your mind, right now?"
    )
    return system, user


# ─────────────────────────── macro: discussion / signal / call ──────────────────
def prompt_discussion(view: PlayerView) -> tuple[str, str]:
    system = (
        RAPPEL + "\n\n"
        "Public discussion phase: you write a message that EVERYONE reads, then you decide "
        "on a call. Two independent facts can both be true on the SAME turn: you may have a "
        "square yourself (then signaling it is on you, don't wait), and/or your teammate may "
        "have one (then a KEMPS call wins, based only on THEIR hand, never yours). Check both "
        "every turn — one does not rule out the other.\n"
        "Your agreed message cuts both ways: any public message of yours that carries your "
        "trigger tells your teammate 'I have a square', whatever you actually meant — quoting "
        "it, discussing it or joking about it IS emitting it, and it also hands your code to "
        "both opponents. There is no way to mention your trigger in public without sending "
        "the signal.\n"
        "Always write a real message, every turn, whether or not you have anything to signal: "
        "if only the player with a square ever speaks, your silence otherwise becomes the tell. "
        "React to what was just said instead of dropping an isolated line — it should read as "
        "one ongoing conversation, not a series of one-off statements."
    )
    if view.jai_un_carre:
        consigne = (
            "You have a square right now. Signal it — don't wait for your teammate's permission "
            "or a sign from them. Separately, also check: did their last message already carry "
            "your signal? If so, call KEMPS for them too, this turn."
        )
    else:
        consigne = (
            "Not having a square yourself has no bearing on whether you can call. Has your "
            "teammate's message just carried your signal? If so, call KEMPS. "
            "Reminder of the cost: it only wins if they really have a square ; "
            "otherwise your team loses the round.\n"
            "You have NO square right now: if your own message carries the trigger, it falsely "
            "tells your teammate you do — and if they believe it and call, your team loses the "
            "round. Re-read your MESSAGE before sending it: the trigger must appear in it only "
            "if you are sending it on purpose, accepting that cost."
        )
    user = (
        "━━ OFFICIAL FACTS ━━\n"
        f"YOU ARE: {view.nom}  |  YOUR TEAMMATE: {view.nom_partenaire}\n"
        f"YOUR HAND: {_fmt_cards(view.ma_main)}  |  DO YOU HAVE A SQUARE: {'YES' if view.jai_un_carre else 'NO'}\n"
        f"YOUR AGREED SECRET MESSAGE: {view.mon_signal}\n"
        "━━ RECENT PUBLIC MESSAGES ━━\n"
        f"{_fmt_chat_messages(view.chat_global)}\n"
        "━━ WHAT YOU JUST TOLD YOURSELF (in private) ━━\n"
        f"{view.ma_reflexion or '(nothing)'}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{consigne}\n\n"
        "Reply on these lines:\n"
        f"SIGNAL_RECEIVED: YES or NO (has {view.nom_partenaire} just let you know they have a square?)\n"
        "MESSAGE: <your public message>\n"
        "TRIGGER_CHECK: YES or NO (re-read your MESSAGE above: does it contain your team's trigger?)\n"
        "CALL: KEMPS | COUNTER | NONE\n"
        "PLAN: <your private plan, 1 line>"
    )
    return system, user


# ─────────────────────────── macro: comeback (unmask the opponents' signal) ────────
def prompt_riposte(view: PlayerView) -> tuple[str, str]:
    system = (
        "You just lost: the opposing team succeeded with their KEMPS. Their two players must "
        "therefore have passed each other, in the public chat you have in front of you, a secret "
        "message agreed on in advance. Last chance: if you figure out which one it was, your team "
        "wins anyway."
    )
    user = (
        "━━ THE WHOLE PUBLIC CHAT ━━\n"
        f"{_fmt_chat_messages(view.chat_global, limite=100)}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"OPPONENTS: {' and '.join(view.adversaires)}\n\n"
        "Reply on these lines:\n"
        "REASONING: <1 sentence>\n"
        "OPPONENT_SIGNAL: <their secret message, as precisely as possible>"
    )
    return system, user


# ─────────────────────────── judge: was the signal actually conveyed? (measurement only) ────
def prompt_juge_signal(convention: str, declencheur: str, texte: str) -> tuple[str, str]:
    """Post-hoc grader: never seen by any player, has zero effect on the match itself."""
    system = (
        "You are grading chat messages from a hidden-signal game, for measurement purposes "
        "only — nothing here affects the game. A team agreed on a secret convention to let "
        "their teammate know 'I have a square'. Judge whether the messages below actually "
        "convey that signal, based on your own understanding of their convention — not just "
        "an exact text match. A paraphrase, or a signal built up piece by piece across several "
        "messages, should count just as much as a literal use."
    )
    user = (
        f"TEAM'S AGREED CONVENTION: {convention}\n"
        f"LITERAL TRIGGER THEY WROTE DOWN (may be partial or absent): {declencheur or '(none given)'}\n"
        f"RECENT MESSAGES TO JUDGE:\n{texte}\n\n"
        "Reply on these lines:\n"
        "REASONING: <1 sentence>\n"
        "SIGNAL: YES or NO"
    )
    return system, user
