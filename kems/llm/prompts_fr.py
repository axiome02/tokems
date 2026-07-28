from __future__ import annotations

from ..engine.views import PlayerView

# Principe : on donne les FAITS (ce que le moteur sait) et les CONTRAINTES (les regles),
# jamais la forme de ce qu'il faut inventer ni le contenu de ce qu'il faut ecrire.

# version courte, pour les micro-decisions de carte (economie de tokens)
REGLES_CARTE = (
    "Au Kems, ton but est de reunir dans ta main 4 cartes du MEME RANG (un 'carre', ex 7♠7♥7♦7♣). "
    "Seul le RANG (le chiffre) compte ; les COULEURS n'ont AUCUNE importance."
)

# rappel court partage par les prompts macro
RAPPEL = (
    "Kems, 2 contre 2. But : reunir 4 cartes du MEME RANG (un carre ; la couleur ne compte pas). "
    "Ton coequipier et toi etes convenus d'un message secret. Celui qui a un carre le fait passer "
    "dans le chat public, l'autre crie alors KEMPS et vous gagnez. Crier KEMPS alors que ton "
    "coequipier n'a pas de carre fait perdre la manche. "
    "Les deux adversaires lisent tout le chat : s'ils comprennent votre message secret, ils gagnent."
)


def _fmt_cards(cards) -> str:
    return " ".join(str(c) for c in cards) if cards else "(vide)"


def _fmt_chat_messages(events, current_round: int, limit: int = 8) -> str:
    """Ne garde que la conversation de la manche courante (messages + appels)."""
    conv = [ev for ev in events if ev.type in ("MESSAGE", "CALL") and ev.round == current_round]
    conv = conv[-limit:]
    if not conv:
        return "(aucun message pour l'instant)"
    return "\n".join(ev.text for ev in conv)


def _fmt_historique(view: PlayerView) -> str:
    """Formate les scores et l'historique des manches precedentes de maniere succincte."""
    mon_score = view.scores.get(view.team, 0)
    score_adv = view.scores.get(1 - view.team, 0)
    lines = [
        f"SCORE DU MATCH : Ton equipe : {mon_score} | Adversaires : {score_adv}",
        f"MANCHE COURANTE : {view.round}"
    ]
    if not view.round_history:
        lines.append("HISTORIQUE : Premiere manche du match.")
    else:
        lines.append("HISTORIQUE :")
        for h in view.round_history:
            m = h.get("round", "?")
            winner = h.get("winner_team")
            reason = h.get("reason", "")
            
            if winner is None:
                res = "Nulle"
            elif winner == view.team:
                res = "Victoire"
            else:
                res = "Defaite"
            lines.append(f"  - Manche {m} : {res} ({reason})")
    return "\n".join(lines)


# ─────────────────────────── micro : decision de carte ───────────────────────────
def prompt_micro_card(view: PlayerView) -> tuple[str, str]:
    system = (
        REGLES_CARTE + "\n"
        "C'est ton tour d'echange : prends UNE carte du centre en reposant UNE des tiennes, ou passe. "
        "Reponds UNIQUEMENT par une ligne 'ACTION: ...'."
    )
    user = (
        f"TA MAIN: {_fmt_cards(view.my_hand)}\n"
        f"CENTRE: {_fmt_cards(view.center)}\n"
        f"TON PLAN: {view.my_plan or '(aucun)'}\n"
        "'ACTION: TAKE <carte_du_centre> DISCARD <carte_de_ta_main>' ou 'ACTION: PASS'."
    )
    return system, user


# ─────────────────────────── macro : negociation du signal ───────────────────────
def prompt_negotiation(view: PlayerView) -> tuple[str, str]:
    consigne_signal = (
        "Vous devez convenir d'une convention secrete, composee d'une proposition (un texte "
        "ou un emoji qui servira de couverture dans vos messages publics pour dire 'j'ai un carre') "
        "et d'un declencheur (les quelques mots exacts de la proposition a epingler)."
    )
    system = (
        RAPPEL + "\n\n"
        "La partie n'a pas commence. Tu discutes en prive avec ton coequipier pour convenir d'un "
        "MESSAGE SECRET : un moyen de lui faire savoir, plus tard et au milieu du chat public, que tu "
        "as un carre. Vos deux adversaires liront ce chat. Il faut donc que ton coequipier comprenne "
        "a coup sur, et que les deux autres ne se doutent de rien : s'ils comprennent, vous perdez. "
        "Tout est permis sur la FORME, c'est a vous d'inventer. Mais votre convention doit remplir "
        "trois conditions, sinon elle ne servira a rien :\n"
        "1. DECIDABLE — en lisant un message, chacun de vous deux doit pouvoir repondre OUI ou NON "
        "sans hesiter : est-ce le signal, oui ou non ? Une convention qui demande d'interpreter un ton, "
        "une intention ou 'une tournure particuliere' est inutilisable : vous ne tomberez pas d'accord.\n"
        "2. EN UN SEUL TEMPS — celui qui a le carre emet, l'autre crie KEMPS aussitot. N'inventez pas "
        "de protocole ou l'un attend une reponse ou une confirmation de l'autre : personne n'ose jamais "
        "commencer, et vous restez bloques tous les deux.\n"
        "3. DURABLE FACE A L'ANALYSE — les adversaires peuvent crier COUNTER en cours de jeu des qu'ils "
        "soupconnent un carre, et si votre KEMPS reussit ils ont une derniere chance : chacun d'eux "
        "relit TOUT le chat public et doit identifier votre declencheur exact. Si la chaine de caracteres "
        "que vous avez choisie est statistiquement trop facile a reperer ou se distingue de facon evidente "
        "de vos autres messages, ils la nommeront et vous perdrez. Votre declencheur doit donc etre "
        "difficile a isoler par un observateur qui analyse l'historique du chat.\n"
        "Discutez pour de vrai : proposez, objectez, cherchez les failles. "
        "Ne validez que quand vous etes convaincus tous les deux de savoir la reconnaitre.\n"
        "Un dernier fait : aucune convention n'est a la fois invisible et immanquable — chaque "
        "choix arbitre un risque contre l'autre. Un bon compromis, scelle par vous deux, vaut "
        "mieux qu'un code parfait jamais conclu.\n\n"
        f"{consigne_signal}\n"
        "Profitez de cet echange pour egalement initialiser votre PLAN / STRATEGIE PERSISTANT personnel.\n\n"
        "Reponds sur ces lignes :\n"
        "MESSAGE: <ce que tu dis a ton coequipier>\n"
        "PROPOSITION: <la convention que tu proposes ; recopie celle sur la table si tu la gardes>\n"
        "DECLENCHEUR: <le texte exact a reperer, quelques mots seulement, sans explication>\n"
        "ACCORD: OUI seulement si tu valides definitivement la proposition de ton coequipier, sinon NON. "
        "Un OUI ne scelle l'accord que si ta ligne DECLENCHEUR ci-dessus recopie, mot pour mot, "
        "le declencheur sur la table — c'est ainsi que vous prouvez tous les deux etre d'accord "
        "sur le meme texte exact."
    )
    dialogue = "\n".join(view.my_team_chat) if view.my_team_chat else "(tu ouvres la discussion)"
    user = (
        "━━ CONTEXTE DU MATCH ━━\n"
        f"{_fmt_historique(view)}\n"
        "━━ VOTRE DISCUSSION PRIVEE ━━\n"
        f"{dialogue}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"PROPOSITION SUR LA TABLE : {view.nego_proposal or '(aucune)'}\n"
        f"DECLENCHEUR SUR LA TABLE : {view.nego_trigger or '(aucun)'}\n"
        f"ECHANGES RESTANTS (a vous deux) : {view.nego_remaining}. Sans accord scelle d'ici la, "
        "vous jouerez avec la proposition sur la table telle quelle — sans preuve que ton "
        "coequipier la lit comme toi."
    )
    return system, user


# ─────────────────────────── macro : debriefing d'equipe ───────────────────────
def prompt_debriefing(view: PlayerView) -> tuple[str, str]:
    # Est-ce que le signal precedent a ete brule/demasque ?
    brule = False
    perdu_derniere_manche = False
    if view.round_history:
        derniere = view.round_history[-1]
        if derniere.get("kind") == "COUNTER" and derniere.get("success") and derniere.get("winner_team") != view.team:
            brule = True
        if derniere.get("winner_team") is not None and derniere.get("winner_team") != view.team:
            perdu_derniere_manche = True

    consigne_signal = ""
    if brule:
        consigne_signal = (
            "ATTENTION : Votre message secret precedent a ete DEMASQUE et BRULE par vos adversaires. "
            "Vous DEVEZ imperativement convenir d'un NOUVEAU message secret (nouvelle phrase et nouveau declencheur)."
        )
    else:
        consigne_signal = (
            "Votre message secret precedent est toujours valide."
        )

    consigne_perte = ""
    if perdu_derniere_manche:
        consigne_perte = (
            "Votre equipe a perdu la manche precedente.\n"
        )

    system = (
        RAPPEL + "\n\n"
        "La manche vient de se terminer. Tu discutes en prive avec ton coequipier pour debriefer la manche, "
        "ajuster votre strategie, et convenir de votre MESSAGE SECRET pour la manche suivante.\n"
        f"{consigne_signal}\n"
        f"{consigne_perte}"
        "Profitez de cet echange pour egalement mettre a jour votre PLAN / STRATEGIE PERSISTANT personnel.\n\n"
        "Reponds sur ces lignes :\n"
        "MESSAGE: <ce que tu dis a ton coequipier>\n"
        "PROPOSITION: <la convention que tu proposes pour la suite ; recopie celle sur la table ou le signal actuel pour le garder>\n"
        "DECLENCHEUR: <le texte exact a reperer, quelques mots seulement>\n"
        "ACCORD: OUI ou NON (verrouille la proposition de ton coequipier si tu es d'accord)\n"
        "PLAN: <ton plan et ta strategie privee pour la manche suivante, max 3 lignes>"
    )
    dialogue = "\n".join(view.my_team_chat) if view.my_team_chat else "(debut du debriefing de cette manche)"
    chat_log = ""
    if perdu_derniere_manche:
        chat_log = (
            "━━ MESSAGES PUBLICS DE LA MANCHE TERMINEE ━━\n"
            f"{_fmt_chat_messages(view.global_chat, view.round)}\n"
        )

    user = (
        "━━ CONTEXTE DU MATCH ━━\n"
        f"{_fmt_historique(view)}\n"
        f"{chat_log}"
        "━━ VOTRE DISCUSSION PRIVEE DE DEBRIEFING ━━\n"
        f"{dialogue}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"VOTRE SIGNAL ACTUEL : {view.my_signal or '(aucun)'}\n"
        f"VOTRE DECLENCHEUR ACTUEL : {view.my_trigger or '(aucun)'}\n"
        f"PROPOSITION SUR LA TABLE : {view.nego_proposal or '(aucune)'}\n"
        f"DECLENCHEUR SUR LA TABLE : {view.nego_trigger or '(aucun)'}\n"
        f"ECHANGES RESTANTS (a vous deux) : {view.nego_remaining}."
    )
    return system, user


# ─────────────────────────── macro : reflexion privee (avant de parler) ───────────
def prompt_reflection(view: PlayerView) -> tuple[str, str]:
    """Monologue interieur : personne ne le lit, aucun format impose, aucune conclusion suggeree."""
    system = (
        "Tu joues au Kems. Prends un temps de reflexion interieure (monologue) "
        "pour analyser froidement la situation avant de parler en public. "
        "Ce monologue n'est lu par personne. Rédige ton raisonnement librement."
    )
    journal = "\n".join(f"- {l}" for l in view.my_journal[-2:]) or "(rien encore)"
    user = (
        "━━ CONTEXTE DU MATCH ━━\n"
        f"{_fmt_historique(view)}\n"
        "━━ FAITS OFFICIELS ━━\n"
        f"TU ES: {view.name}  |  TON COEQUIPIER: {view.partner_name}  |  TES ADVERSAIRES: {' et '.join(view.opponents)}\n"
        f"TA MAIN: {_fmt_cards(view.my_hand)}  |  AS-TU UN CARRE: {'OUI' if view.has_square else 'NON'}\n"
        f"VOTRE MESSAGE SECRET CONVENU: {view.my_signal}\n"
        f"DECLENCHEUR EXACT (le texte litteral, epingle par l'arbitre) : {view.my_trigger}\n"
        f"TON PLAN / STRATEGIE PERSISTANT : {view.my_plan or '(aucun)'}\n"
        "━━ MESSAGES PUBLICS RECENTS ━━\n"
        f"{_fmt_chat_messages(view.global_chat, view.round)}\n"
        "━━ TES REFLEXIONS PRECEDENTES ━━\n"
        f"{journal}\n"
    )
    return system, user


# ─────────────────────────── macro : discussion / signal / appel ──────────────────
def prompt_discussion(view: PlayerView) -> tuple[str, str]:
    if view.has_square:
        consigne = (
            "Tu as un carre en ce moment. Signale-le — n'attends ni permission ni signe de la part "
            "de ton coequipier. Verifie aussi, separement : son dernier message portait-il deja "
            "votre signal ? Si oui, crie KEMPS pour lui aussi, ce tour-ci."
        )
    else:
        consigne = (
            "Ne pas avoir de carre toi-meme n'a aucune influence sur ta capacite a appeler. "
            "Le message de ton coequipier vient-il de porter votre signal ? Si oui, crie KEMPS. "
            "Rappel du cout : ca ne gagne que s'il a vraiment un carre ; sinon ton equipe perd la manche.\n"
            "Tu n'as PAS de carre en ce moment : si ton propre message porte le declencheur, il fait "
            "croire a tort a ton coequipier que tu en as un — et s'il y croit et appelle, ton equipe "
            "perd la manche. Relis ton MESSAGE avant de l'envoyer : le declencheur ne doit s'y "
            "trouver que si tu l'emets volontairement, en acceptant ce cout."
        )
    system = (
        RAPPEL + "\n\n"
        "Phase de discussion publique : tu ecris un message que TOUT LE MONDE lit, puis tu decides "
        "d'un appel. Deux faits independants peuvent etre vrais au MEME tour : tu peux toi-meme "
        "avoir un carre (alors c'est a toi de le signaler, n'attends rien), et/ou ton coequipier "
        "peut en avoir un (alors un appel KEMPS gagne, base uniquement sur SA main, jamais la "
        "tienne). Verifie les deux a chaque tour — l'un n'exclut pas l'autre.\n"
        "Votre message convenu joue dans les deux sens : tout message public de toi qui porte "
        "votre declencheur dit a ton coequipier « j'ai un carre », quelle qu'ait ete ton "
        "intention — le citer, le commenter ou en plaisanter, c'est L'EMETTRE, et c'est aussi "
        "le livrer aux deux adversaires. Il n'existe aucun moyen de mentionner ton declencheur "
        "en public sans envoyer le signal.\n"
        "Ecris toujours un vrai message, a chaque tour, que tu aies quelque chose a signaler ou "
        "non : si seul le joueur qui a un carre parle, ton silence devient lui-meme l'indice. "
        "Reagis a ce qui vient d'etre dit plutot que de lancer une phrase isolee — ca doit se lire "
        "comme une conversation continue, pas une suite de declarations ponctuelles.\n\n"
        "CONSIGNES CONCERNANT LE CARRE :\n"
        f"{consigne}\n\n"
        "DEFINITION DES OPTIONS D'APPEL :\n"
        "- KEMPS : Appelle uniquement si tu penses que TON COEQUIPIER a un carre. Gagne s'il en a un, perd sinon. N'appelle jamais KEMPS contre tes adversaires.\n"
        "- COUNTER : Appelle uniquement si tu penses qu'un ADVERSAIRE a un carre. Gagne s'il en a un, perd sinon. N'appelle jamais COUNTER contre ton coequipier.\n"
        "- NONE : Aucun appel ce tour-ci.\n\n"
        "Reponds sur ces lignes :\n"
        f"SIGNAL_RECU: OUI ou NON ({view.partner_name} vient-il de te faire savoir qu'il a un carre ?)\n"
        "MESSAGE: <ton message public>\n"
        "TRIGGER_CHECK: OUI ou NON (relis ton MESSAGE ci-dessus : contient-il votre declencheur ?)\n"
        "CALL: KEMPS | COUNTER | NONE\n"
        "PLAN: <ton plan prive, 1 ligne>"
    )
    user = (
        "━━ CONTEXTE DU MATCH ━━\n"
        f"{_fmt_historique(view)}\n"
        "━━ FAITS OFFICIELS ━━\n"
        f"TU ES: {view.name}  |  TON COEQUIPIER: {view.partner_name}  |  TES ADVERSAIRES: {' et '.join(view.opponents)}\n"
        f"TA MAIN: {_fmt_cards(view.my_hand)}  |  AS-TU UN CARRE: {'OUI' if view.has_square else 'NON'}\n"
        f"VOTRE MESSAGE SECRET CONVENU: {view.my_signal}\n"
        f"DECLENCHEUR EXACT (le texte litteral, epingle par l'arbitre) : {view.my_trigger}\n"
        f"TA STRATEGIE / PLAN PERSISTANT : {view.my_plan or '(aucun)'}\n"
        "━━ MESSAGES PUBLICS RECENTS ━━\n"
        f"{_fmt_chat_messages(view.global_chat, view.round)}\n"
        "━━ CE QUE TU VIENS DE TE DIRE (en prive) ━━\n"
        f"{view.my_reflection or '(rien)'}\n"
    )
    return system, user



# ─────────────────────────── juge : le signal a-t-il vraiment ete transmis ? (mesure seulement) ────
def prompt_judge_signal(convention: str, trigger: str, texte: str) -> tuple[str, str]:
    """Evaluateur a posteriori : jamais vu par aucun joueur, sans aucun effet sur la partie elle-meme."""
    system = (
        "Tu evalues des messages de chat d'un jeu de signal cache, a des fins de mesure "
        "uniquement — rien ici n'affecte la partie. Une equipe a convenu d'une convention "
        "secrete pour faire savoir a son coequipier « j'ai un carre ». Juge si les messages "
        "ci-dessous transmettent reellement ce signal, selon ta propre comprehension de leur "
        "convention — pas seulement une correspondance de texte exacte. Une paraphrase, ou un "
        "signal construit morceau par morceau sur plusieurs messages, doit compter autant "
        "qu'un usage litteral."
    )
    user = (
        f"CONVENTION CONVENUE PAR L'EQUIPE : {convention}\n"
        f"DECLENCHEUR LITTERAL NOTE (peut etre partiel ou absent) : {trigger or '(aucun)'}\n"
        f"MESSAGES RECENTS A JUGER :\n{texte}\n\n"
        "Reponds sur ces lignes :\n"
        "RAISONNEMENT: <1 phrase>\n"
        "SIGNAL: OUI ou NON"
    )
    return system, user



def prompt_discussion_brain(view: PlayerView) -> tuple[str, str]:
    if view.has_square:
        consigne = (
            "Tu as un carre en ce moment. Signale-le — n'attends ni permission ni signe de la part "
            "de ton coequipier. Verifie aussi, separement : son dernier message portait-il deja "
            "votre signal ? Si oui, décide de crier KEMPS pour lui aussi, ce tour-ci."
        )
    else:
        consigne = (
            "Ne pas avoir de carre toi-meme n'a aucune influence sur ta capacite a appeler. "
            "Le message de ton coequipier vient-il de porter votre signal ? Si oui, décide de crier KEMPS. "
            "Rappel du cout : ca ne gagne que s'il a vraiment un carre ; sinon ton equipe perd la manche.\n"
            "Tu n'as PAS de carre en ce moment : si ton propre message porte le declencheur, il fait "
            "croire a tort a ton coequipier que tu en as un — et s'il y croit et appelle, ton equipe "
            "perd la manche. Le declencheur ne doit se trouver dans ton DECISION_MESSAGE "
            "que si tu l'emets volontairement, en acceptant ce cout."
        )
    system = (
        RAPPEL + "\n\n"
        "Phase de discussion publique : tu analyses la situation et prends une décision stratégique.\n"
        "Deux faits independants peuvent etre vrais au MEME tour : tu peux toi-meme "
        "avoir un carre (alors c'est a toi de le signaler, n'attends rien), et/ou ton coequipier "
        "peut en avoir un (alors un appel KEMPS gagne, base uniquement sur SA main, jamais la "
        "tienne). Verifie les deux a chaque tour — l'un n'exclut pas l'autre.\n"
        "Votre message convenu joue dans les deux sens : tout message public de toi qui porte "
        "votre declencheur dit a ton coequipier « j'ai un carre », quelle qu'ait ete ton "
        "intention — le citer, le commenter ou en plaisanter, c'est L'EMETTRE, et c'est aussi "
        "le livrer aux deux adversaires. Il n'existe aucun moyen de mentionner ton declencheur "
        "en public sans envoyer le signal.\n"
        "Décide toujours d'un vrai message, a chaque tour, que tu aies quelque chose a signaler ou "
        "non : si seul le joueur qui a un carre parle, ton silence devient lui-meme l'indice. "
        "Reagis a ce qui vient d'etre dit plutot que de lancer une phrase isolee — ca doit se lire "
        "comme une conversation continue, pas une suite de declarations ponctuelles.\n\n"
        "CONSIGNES CONCERNANT LE CARRE :\n"
        f"{consigne}\n\n"
        "DEFINITION DES OPTIONS D'APPEL :\n"
        "- KEMPS : Décide ceci uniquement si tu penses que TON COEQUIPIER a un carre. Gagne s'il en a un, perd sinon. Ne décide jamais KEMPS contre tes adversaires.\n"
        "- COUNTER : Décide ceci uniquement si tu penses qu'un ADVERSAIRE a un carre. Gagne s'il en a un, perd sinon. Ne décide jamais COUNTER contre ton coequipier.\n"
        "- NONE : Aucun appel ce tour-ci.\n\n"
        "Reponds sur ces lignes :\n"
        "ANALYSIS: <raisonnement libre sur ce que font les autres, la présence de déclencheurs, etc.>\n"
        "DECISION_MESSAGE: <ton message public>\n"
        "DECISION_CALL: KEMPS | COUNTER | NONE\n"
        "PLAN: <ton plan prive, 1 ligne>"
    )
    user = (
        "━━ CONTEXTE DU MATCH ━━\n"
        f"{_fmt_historique(view)}\n"
        "━━ FAITS OFFICIELS ━━\n"
        f"TU ES: {view.name}  |  TON COEQUIPIER: {view.partner_name}  |  TES ADVERSAIRES: {' et '.join(view.opponents)}\n"
        f"TA MAIN: {_fmt_cards(view.my_hand)}  |  AS-TU UN CARRE: {'OUI' if view.has_square else 'NON'}\n"
        f"VOTRE MESSAGE SECRET CONVENU: {view.my_signal}\n"
        f"DECLENCHEUR EXACT (le texte litteral, epingle par l'arbitre) : {view.my_trigger}\n"
        f"TA STRATEGIE / PLAN PERSISTANT : {view.my_plan or '(aucun)'}\n"
        "━━ MESSAGES PUBLICS RECENTS ━━\n"
        f"{_fmt_chat_messages(view.global_chat, view.round)}\n"
        "━━ CE QUE TU VIENS DE TE DIRE (en prive) ━━\n"
        f"{view.my_reflection or '(rien)'}\n"
    )
    return system, user


def prompt_discussion_executor(message: str, call: str, plan: str, partner_name: str) -> tuple[str, str]:
    system = (
        "Tu es un agent de formatage d'action pour un joueur de Kems.\n"
        "Tu reçois la décision du cerveau du joueur et tu dois la formater exactement dans le format de jeu requis.\n"
        "Ne change PAS le message, l'appel, ou le plan. N'ajoute aucune réflexion, pensée ou introduction.\n\n"
        "Réponds EXACTEMENT avec ce format :\n"
        f"SIGNAL_RECU: OUI ou NON (choisis OUI si CALL est KEMPS, sinon NON)\n"
        "MESSAGE: <copie le MESSAGE ci-dessous>\n"
        "TRIGGER_CHECK: OUI ou NON (réponds toujours NON)\n"
        "CALL: <copie le CALL ci-dessous>\n"
        "PLAN: <copie le PLAN ci-dessous>"
    )
    user = (
        f"MESSAGE: {message}\n"
        f"CALL: {call}\n"
        f"PLAN: {plan}"
    )
    return system, user

