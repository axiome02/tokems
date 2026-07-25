from __future__ import annotations

from ..engine.views import PlayerView

# Principle: we give the FACTS (what the engine knows) and the CONSTRAINTS (the rules),
# never the form of what needs to be invented nor the content of what needs to be written.

# short version, for card micro-decisions (token savings)
REGLES_CARTE = (
    "In Kems, your goal is to gather 4 cards of the SAME RANK in your hand (a 'square', e.g. 7♠7♥7♦7♣). "
    "Only the RANK (the number) matters ; SUITS have NO importance."
)

# short reminder shared by macro prompts
RAPPEL = (
    "Kems, 2 vs 2. Goal: gather 4 cards of the SAME RANK (a square; suit doesn't matter). "
    "You and your teammate agreed on a secret message. Whoever has a square passes it "
    "in the public chat, the other then calls KEMPS and you win. Calling KEMPS when your "
    "teammate has no square makes you lose the round. "
    "Both opponents read all chat: if they figure out your secret message, they win."
)


def _fmt_cards(cards) -> str:
    return " ".join(str(c) for c in cards) if cards else "(empty)"


def _fmt_chat_messages(events, current_manche: int, limite: int = 8) -> str:
    """Only keep conversation of the current round (messages + calls)."""
    conv = [ev for ev in events if ev.type in ("MESSAGE", "CALL") and ev.manche == current_manche]
    conv = conv[-limite:]
    if not conv:
        return "(no messages yet)"
    return "\n".join(ev.texte for ev in conv)


def _fmt_historique(view: PlayerView) -> str:
    """Format scores and history of past rounds in a succinct manner."""
    mon_score = view.scores.get(view.equipe, 0)
    score_adv = view.scores.get(1 - view.equipe, 0)
    lines = [
        f"MATCH SCORE: Your team: {mon_score} | Opponents: {score_adv}",
        f"CURRENT ROUND: {view.manche}"
    ]
    if not view.historique_manches:
        lines.append("HISTORY: First round of the match.")
    else:
        lines.append("HISTORY:")
        for h in view.historique_manches:
            m = h.get("manche", "?")
            winner = h.get("winner_team")
            reason = h.get("reason", "")
            
            if winner is None:
                res = "Draw"
            elif winner == view.equipe:
                res = "Win"
            else:
                res = "Loss"
            lines.append(f"  - Round {m}: {res} ({reason})")
    return "\n".join(lines)


# ─────────────────────────── micro: card decision ───────────────────────────
def prompt_micro_carte(view: PlayerView) -> tuple[str, str]:
    system = (
        REGLES_CARTE + "\n"
        "It's your exchange turn: take ONE card from the center and discard ONE of yours, or pass. "
        "Reply ONLY with a line 'ACTION: ...'."
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
    consigne_signal = (
        "You must agree on a secret convention, consisting of a proposition (a text or emoji "
        "used as cover in public messages to say 'I have a square') and a trigger (the exact few words "
        "of the proposition to pin)."
    )
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
        "3. RESISTANT TO ANALYSIS — the opponents can call COUNTER during play the moment they "
        "suspect a square, and if your KEMPS succeeds they get one last chance: each of them "
        "re-reads the ENTIRE public chat and must identify your exact trigger. If the text string "
        "you choose is statistically too easy to isolate or stands out obviously from your other "
        "messages, they will name it and you will lose. Your trigger must therefore be difficult "
        "for an observer analyzing the chat log history to isolate.\n"
        "Discuss for real: propose, object, look for the flaws. "
        "Only lock it in once you're both convinced you can recognize it.\n"
        "One last fact: no convention is both invisible and unmistakable — every choice trades "
        "one risk against the other. A good-enough compromise, sealed by both of you, beats a "
        "perfect one that never gets agreed on.\n\n"
        f"{consigne_signal}\n"
        "Use this exchange to also initialize your personal PERSISTENT PLAN / STRATEGY.\n\n"
        "Reply on these lines:\n"
        "MESSAGE: <what you say to your teammate>\n"
        "PROPOSAL: <the convention you're proposing ; copy the one on the table if you're keeping it>\n"
        "TRIGGER: <the exact text to spot, just a few words, no explanation>\n"
        "AGREE: YES only if you're definitively locking in your teammate's proposal, otherwise NO. "
        "A YES only seals the deal if your TRIGGER line above restates, word for word, the "
        "trigger on the table — that's how you both prove you agreed on the same exact text."
    )
    dialogue = "\n".join(view.mon_chat_equipe) if view.mon_chat_equipe else "(you're opening the discussion)"
    user = (
        "━━ MATCH CONTEXT ━━\n"
        f"{_fmt_historique(view)}\n"
        "━━ YOUR PRIVATE DISCUSSION ━━\n"
        f"{dialogue}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"PROPOSAL ON THE TABLE: {view.nego_proposition or '(none)'}\n"
        f"TRIGGER ON THE TABLE: {view.nego_declencheur or '(none)'}\n"
        f"EXCHANGES REMAINING (you two combined): {view.nego_restants}. If nothing is sealed "
        "by then, you'll play with the proposal on the table as it stands — with no proof your "
        "teammate reads it the same way you do."
    )
    return system, user


# ─────────────────────────── macro: team debriefing ───────────────────────
def prompt_debriefing(view: PlayerView) -> tuple[str, str]:
    from ..engine import rules
    brule = False
    if view.historique_manches:
        derniere = view.historique_manches[-1]
        rip = derniere.get("riposte")
        if rip and rip.get("reussie", False) and rip.get("equipe") != view.equipe:
            brule = True

    consigne_signal = ""
    if brule:
        consigne_signal = (
            "WARNING: Your previous secret message was UNMASKED and BURNED by the opponents. "
            "You MUST agree on a NEW secret message (new phrase and new trigger)."
        )
    else:
        consigne_signal = (
            "Your previous secret message is still valid. However, to prevent opponents from "
            "eventually figuring it out, you can choose to keep it or proactively change/rotate it."
        )

    system = (
        RAPPEL + "\n\n"
        "The round has just ended. You are talking privately with your teammate to debrief the round, "
        "adjust your strategy, and agree on your SECRET MESSAGE for the next round.\n"
        f"{consigne_signal}\n"
        "Use this exchange to also update your personal PERSISTENT PLAN / STRATEGY.\n\n"
        "Reply on these lines:\n"
        "MESSAGE: <what you say to your teammate>\n"
        "PROPOSAL: <the convention you propose for the next round ; copy the one on the table or the current signal to keep it>\n"
        "TRIGGER: <the exact text to spot, just a few words>\n"
        "AGREE: YES or NO (lock in your teammate's proposal if you agree)\n"
        "PLAN: <your private plan and strategy for the next round, max 3 lines>"
    )
    dialogue = "\n".join(view.mon_chat_equipe) if view.mon_chat_equipe else "(start of debriefing for this round)"
    user = (
        "━━ MATCH CONTEXT ━━\n"
        f"{_fmt_historique(view)}\n"
        "━━ YOUR PRIVATE DEBRIEFING DISCUSSION ━━\n"
        f"{dialogue}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"YOUR CURRENT SIGNAL: {view.mon_signal or '(none)'}\n"
        f"YOUR CURRENT TRIGGER: {view.mon_declencheur or '(none)'}\n"
        f"PROPOSAL ON THE TABLE: {view.nego_proposition or '(none)'}\n"
        f"TRIGGER ON THE TABLE: {view.nego_declencheur or '(none)'}\n"
        f"EXCHANGES REMAINING (you two combined): {view.nego_restants}."
    )
    return system, user


# ─────────────────────────── macro: private reflection (before speaking) ───────────
def prompt_reflexion(view: PlayerView) -> tuple[str, str]:
    """Inner monologue: nobody reads it, no imposed format, no suggested conclusion."""
    system = (
        "You play Kems. Take a moment to think (inner monologue) "
        "to analyze the situation before speaking in public. "
        "This monologue is read by no one. Write your thoughts freely."
    )
    journal = "\n".join(f"- {l}" for l in view.mon_journal[-2:]) or "(nothing yet)"
    user = (
        "━━ MATCH CONTEXT ━━\n"
        f"{_fmt_historique(view)}\n"
        "━━ OFFICIAL FACTS ━━\n"
        f"YOU ARE: {view.nom}  |  YOUR TEAMMATE: {view.nom_partenaire}  |  YOUR OPPONENTS: {' and '.join(view.adversaires)}\n"
        f"YOUR HAND: {_fmt_cards(view.ma_main)}  |  DO YOU HAVE A SQUARE: {'YES' if view.jai_un_carre else 'NO'}\n"
        f"YOUR AGREED SECRET MESSAGE: {view.mon_signal}\n"
        f"EXACT TRIGGER (the literal text, as pinned by the referee): {view.mon_declencheur}\n"
        f"YOUR PLAN / PERSISTENT STRATEGY: {view.mon_plan or '(none)'}\n"
        "━━ RECENT PUBLIC MESSAGES ━━\n"
        f"{_fmt_chat_messages(view.chat_global, view.manche)}\n"
        "━━ YOUR PREVIOUS THOUGHTS ━━\n"
        f"{journal}\n"
    )
    return system, user


# ─────────────────────────── macro: discussion / signal / call ──────────────────
def prompt_discussion(view: PlayerView) -> tuple[str, str]:
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
        "one ongoing conversation, not a series of one-off statements.\n\n"
        "SQUARE GUIDELINES:\n"
        f"{consigne}\n\n"
        "CALL OPTIONS DEFINITIONS:\n"
        "- KEMPS: Call this ONLY if you believe YOUR TEAMMATE has a square. It wins if they do, and loses otherwise.\n"
        "- COUNTER: Call this ONLY if you believe an OPPONENT has a square. It wins if they do, and loses otherwise. Never call COUNTER against your teammate.\n"
        "- NONE: No call this turn.\n\n"
        "Reply on these lines:\n"
        f"SIGNAL_RECEIVED: YES or NO (has {view.nom_partenaire} just let you know they have a square?)\n"
        "MESSAGE: <your public message>\n"
        "TRIGGER_CHECK: YES or NO (re-read your MESSAGE above: does it contain your team's trigger?)\n"
        "CALL: KEMPS | COUNTER | NONE\n"
        "PLAN: <your private plan, 1 line>"
    )
    user = (
        "━━ MATCH CONTEXT ━━\n"
        f"{_fmt_historique(view)}\n"
        "━━ OFFICIAL FACTS ━━\n"
        f"YOU ARE: {view.nom}  |  YOUR TEAMMATE: {view.nom_partenaire}  |  YOUR OPPONENTS: {' and '.join(view.adversaires)}\n"
        f"YOUR HAND: {_fmt_cards(view.ma_main)}  |  DO YOU HAVE A SQUARE: {'YES' if view.jai_un_carre else 'NO'}\n"
        f"YOUR AGREED SECRET MESSAGE: {view.mon_signal}\n"
        f"EXACT TRIGGER (the literal text, as pinned by the referee): {view.mon_declencheur}\n"
        f"YOUR PLAN / PERSISTENT STRATEGY: {view.mon_plan or '(none)'}\n"
        "━━ RECENT PUBLIC MESSAGES ━━\n"
        f"{_fmt_chat_messages(view.chat_global, view.manche)}\n"
        "━━ WHAT YOU JUST TOLD YOURSELF (in private) ━━\n"
        f"{view.ma_reflexion or '(nothing)'}\n"
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
        "━━ ALL PUBLIC CHAT ━━\n"
        f"{_fmt_chat_messages(view.chat_global, view.manche, limite=100)}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"OPPONENTS: {' and '.join(view.adversaires)}\n\n"
        "Reply on these lines:\n"
        "REASONING: <1 sentence>\n"
        "SIGNAL_ADVERSE: <their secret message, as precisely as possible>"
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


# ─────────────────────────── judge: is the opponents' comeback attempt correct? ────
def prompt_juge_riposte(convention: str, declencheur: str, reponse: str) -> tuple[str, str]:
    """comeback grader: judge if the opponents' guess unmasked the signal semantically."""
    system = (
        "You are a neutral and impartial referee of Kems. Your role is to judge if a player "
        "has successfully unmasked the opposing team's secret message. The opposing team had agreed "
        "on a secret convention. The player attempted a guess to name that signal. "
        "Evaluate if the player correctly identified and understood the secret semantically "
        "(even if they use paraphrases, explanations, synonyms, or correctly describe the structure "
        "of the signal such as punctuation or emojis).\n"
        "Reply ONLY with 'SIGNAL: YES' or 'SIGNAL: NO' after a brief reasoning."
    )
    user = (
        f"OPPOSING SECRET CONVENTION: {convention}\n"
        f"SIGNAL TRIGGER: {declencheur}\n"
        f"PLAYER'S GUESS: {reponse}\n\n"
        "Did the player understand/unmask the secret signal?\n"
        "Reply on these lines:\n"
        "REASONING: <1 explanatory sentence>\n"
        "SIGNAL: YES or NO"
    )
    return system, user
