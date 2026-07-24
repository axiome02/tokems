from __future__ import annotations

import hashlib
from random import Random

from .config import Config
from .engine import rules
from .engine.actions import Call, Take
from .engine.cards import construire_paquet, est_carre
from .engine.signaux import AUCUN_SIGNAL, normaliser
from .engine.state import Event, GameState, Player
from .engine.views import vue_pour
from .i18n import t

# identifiants neutres : un prenom porte des connotations qui influencent les modeles.
# Traduit selon la langue de partie : ces noms sont ecrits mot pour mot dans les prompts,
# un "Joueur 1" dans un prompt anglais recreerait la derive linguistique deja observee.
def _nom(pid: int, lang: str = "en") -> str:
    return t(lang, "player_label", n=pid + 1)


def _derive(master: int, label: str) -> int:
    h = hashlib.sha256(f"{master}:{label}".encode()).hexdigest()
    return int(h[:16], 16)


def setup(config: Config, modeles: list[str]) -> GameState:
    rng_cards = Random(config.seed_cards if config.seed_cards is not None
                       else _derive(config.master_seed, "cards"))
    rng_order = Random(config.seed_order if config.seed_order is not None
                       else _derive(config.master_seed, "order"))

    players = [
        Player(pid=i, nom=_nom(i, config.lang), equipe=i % 2, modele=modeles[i])
        for i in range(config.nb_joueurs)
    ]

    deck = construire_paquet(config.nb_rangs)
    rng_cards.shuffle(deck)

    hands = {p.pid: [deck.pop() for _ in range(config.taille_main)] for p in players}
    center = [deck.pop() for _ in range(config.taille_centre)]

    state = GameState(
        config=config,
        players=players,
        hands=hands,
        center=center,
        deck=deck,
        discard=[],
        signals={},
        plans={p.pid: "" for p in players},
        journaux={p.pid: [] for p in players},
        team_channels={0: [], 1: []},
        public_log=[],
        rng_cards=rng_cards,
        rng_order=rng_order,
    )
    state.public_log.append(
        Event(0, "SYSTEM", None,
              t(config.lang, "start_game", seed=config.master_seed, rangs=config.nb_rangs))
    )
    return state


def nouvelle_manche(state: GameState) -> None:
    """Redistribue tout pour la manche suivante. Le chat public, lui, ne s'efface jamais."""
    state.manche += 1
    state.tour += 1                 # la nouvelle donne appartient deja au 1er tour de la manche
    state.tour_manche = 1
    state.centres_joues = 0
    state.finished = False
    state.outcome = None
    state.riposte_equipe = None

    deck = construire_paquet(state.config.nb_rangs)
    state.rng_cards.shuffle(deck)
    state.hands = {p.pid: [deck.pop() for _ in range(state.config.taille_main)] for p in state.players}
    state.center = [deck.pop() for _ in range(state.config.taille_centre)]
    state.deck = deck
    state.discard = []
    rules._log(state, "SYSTEM", None,
               t(state.config.lang, "new_deal", manche=state.manche,
                 s0=state.scores[0], s1=state.scores[1]))


def _ordre(state: GameState) -> list[int]:
    ordre = [p.pid for p in state.players]
    state.rng_order.shuffle(ordre)
    return ordre


def _extras_decision(view, agent, action_str: str) -> dict:
    """Extras attaches a l'etape de timeline qui porte une DECISION : l'action decidee, la main
    du decideur au moment de decider, et l'echange LLM brut (prompt, reponse). Flux
    d'observabilite UNIQUE : le transcript debug filtre la timeline sur la presence de `action`
    (le dashboard, lui, ignore les champs lourds — voir dashboard._instantane)."""
    io = getattr(agent, "last_io", None)
    return {
        "action": action_str,
        "main": [str(c) for c in view.ma_main],
        "carre": view.jai_un_carre,
        "prompt_user": io[1] if io else None,
        "reponse_brute": io[2] if io else None,
    }


def negotiation(state: GameState, agents: dict, equipes: tuple[int, ...] | None = None) -> None:
    """Vraie discussion alternee A<->B par equipe pour converger vers le meilleur signal.

    Chaque tour, le joueur voit le dialogue en cours + la proposition sur la table ; il
    propose/affine, ou verrouille (ACCORD: OUI) la proposition faite par son coequipier.
    On s'arrete des qu'un accord porte sur la proposition de l'AUTRE joueur (garantit au
    moins un aller-retour), sinon au bout de max_tours_negociation (fige la derniere proposition).

    Scellage NOTARIE (anti-confabulation, cf. game_42_large_v2) : un accord — explicite ou
    tacite — ne clot la negociation que si (a) le declencheur sur la table est EXPLOITABLE
    (concret, pas une meta-politique) et (b) l'accordeur RE-ECRIT lui-meme ce declencheur
    (read-back : les deux joueurs ont alors ecrit independamment la meme chaine litterale —
    la comprehension partagee est prouvee, pas supposee). Le moteur ne dicte rien du contenu :
    il refuse d'authentifier un contrat sans sa clause essentielle. Sans scellage au plafond,
    on fige comme avant et `state.nego_convergence[equipe] = False` le MESURE.
    """
    state.phase = "NEGOTIATION"
    for equipe in equipes if equipes is not None else (0, 1):
        joueurs = state.joueurs_equipe(equipe)
        proposition = ""
        declencheur = ""
        proposeur: int | None = None  # qui a fait la proposition actuellement sur la table
        scelle = False
        for nt in range(state.config.max_tours_negociation):
            pid = joueurs[nt % len(joueurs)]
            view = vue_pour(state, pid, nego_proposition=proposition,
                            nego_declencheur=declencheur,
                            nego_restants=state.config.max_tours_negociation - nt)
            n = agents[pid].negotiate(view)
            nom = state.players[pid].nom
            if n.message:
                state.team_channels[equipe].append(f"{nom}: {n.message}")
            accord_mot = t(state.config.lang, "yes_word" if n.accord else "no_word")
            rules.etape(state, "NEGOTIATION", pid,
                        t(state.config.lang, "negotiating", nom=nom), prive=n.message,
                        proposition=n.proposition, declencheur=n.declencheur, accord=n.accord,
                        **_extras_decision(view, agents[pid],
                                           f"MESSAGE='{n.message}' PROPOSITION='{n.proposition}' "
                                           f"DECLENCHEUR='{n.declencheur}' ACCORD={accord_mot}"))
            # Accord valable seulement sur une proposition faite par le coequipier — explicite
            # (ACCORD: OUI) ou tacite : recopier mot pour mot la proposition sur la table, c'est
            # la garder. Sans cette seconde branche les modeles s'echangent la meme phrase
            # jusqu'a epuiser max_tours_negociation (~12 appels de remplissage par partie).
            echo = bool(n.proposition and proposition
                        and normaliser(n.proposition) == normaliser(proposition))
            # read-back : l'accordeur re-ecrit le declencheur de la table, a l'identique
            readback = bool(declencheur and n.declencheur
                            and normaliser(n.declencheur) == normaliser(declencheur))
            if ((n.accord or echo) and proposition and proposeur is not None
                    and proposeur != pid and readback
                    and rules.declencheur_exploitable(declencheur)):
                scelle = True
                break
            if n.proposition:
                proposition, proposeur = n.proposition, pid
                declencheur = n.declencheur or ""
        state.nego_convergence[equipe] = scelle
        rules.poser_signal(state, equipe, proposition or AUCUN_SIGNAL, declencheur)


def exchange_phase(state: GameState, agents: dict) -> None:
    state.phase = "EXCHANGE"
    cfg = state.config
    st = 0
    while st < cfg.max_sous_tours_par_centre:
        un_take = False
        for pid in _ordre(state):
            nom = state.players[pid].nom
            if est_carre(state.hands[pid]):
                # episode ouvert en silence : le chat est public, un carre est prive.
                # Le joueur decide quand meme s'il garde ou casse son carre : ce n'est
                # pas au moteur de juger a sa place que le garder est la seule option sensee.
                rules.ouvrir_episode(state, pid)
            view = vue_pour(state, pid)
            action = agents[pid].decide_card(view)
            if isinstance(action, Take):
                if rules.valider_et_appliquer_echange(state, pid, action):
                    rules._log(state, "SWAP", pid,
                               t(state.config.lang, "takes_discards", nom=nom,
                                 prise=str(action.from_center), repose=str(action.discard)),
                               prise=str(action.from_center), repose=str(action.discard),
                               **_extras_decision(view, agents[pid],
                                                  f"TAKE {action.from_center} DISCARD {action.discard}"))
                    un_take = True
                    if est_carre(state.hands[pid]):
                        # episode ouvert en silence : le chat est public, un carre est prive
                        rules.ouvrir_episode(state, pid)
                else:
                    rules._log(state, "SYSTEM", pid, t(state.config.lang, "illegal_exchange", nom=nom),
                               **_extras_decision(view, agents[pid],
                                                  f"ILLEGAL {action.from_center}/{action.discard} -> PASS"))
            else:
                rules._log(state, "PASS", pid, t(state.config.lang, "passes", nom=nom),
                           **_extras_decision(view, agents[pid], "PASS"))
        st += 1
        if not un_take:
            break
    rules.resoudre_poubelle(state)
    rules._log(state, "SWEEP", None,
               t(state.config.lang, "center_swept",
                 cartes=" ".join(str(c) for c in state.center)))


def _texte_recent(state: GameState, limite: int = 8) -> str:
    """Fenetre du chat public de la manche en cours, pour le juge LLM (mesure)."""
    conv = [ev for ev in state.public_log
            if ev.type in ("MESSAGE", "CALL") and ev.manche == state.manche]
    conv = conv[-limite:]
    return "\n".join(ev.texte for ev in conv)


def _juger_transmission_kemps(state: GameState, agents: dict) -> None:
    """Jugement LLM independant (PURE MESURE, n'affecte jamais le resultat) : le signal de
    l'equipe appelante a-t-il vraiment circule, au-dela de ce que le moteur sait detecter
    litteralement ?
    """
    if not state.config.evaluer_signaux:
        return
    o = state.outcome
    if not o or o.get("kind") != "KEMPS":
        return
    equipe = state.equipe_de(o["caller"])
    convention = state.signals.get(equipe, "")
    declencheur = state.declencheurs.get(equipe, "")
    texte = _texte_recent(state)
    if texte:
        # sous filet : une mesure qui echoue (429, reseau) ne tue jamais la partie
        try:
            evaluateur = agents.get("evaluateur") or agents.get(0)
            if evaluateur is not None:
                o["signal_reellement_emis_llm"] = evaluateur.juger_signal(convention, declencheur, texte)
        except Exception:
            pass


def discussion_phase(state: GameState, agents: dict) -> None:
    state.phase = "DISCUSSION"
    # plusieurs passes de parole par tour (chacun parle N fois) : la premiere passe expose
    # les signaux emis ce tour-ci, la suivante laisse le partenaire y reagir dans la FOULEE
    # au lieu d'attendre le tour d'apres (cf. lecon #10, deadlock du double-carre).
    for _ in range(state.config.tours_discussion):
        ordre = _ordre(state)
        calls: dict[int, Call] = {}
        for pid in ordre:
            # 1) le joueur reflechit pour lui-meme, sans contrainte de format ni de conclusion.
            #    On saute l'appel quand il n'a rien de neuf a penser : pas de carre et aucun
            #    message public depuis sa derniere reflexion (il ruminait a vide, cf. partie 606).
            journal = state.journaux.setdefault(pid, [])
            vus = sum(1 for ev in state.public_log if ev.type in ("MESSAGE", "CALL"))
            if journal and not est_carre(state.hands[pid]) and vus == state.vu_a_la_reflexion.get(pid):
                reflexion = journal[-1]
            else:
                vue_reflexion = vue_pour(state, pid)
                reflexion = agents[pid].reflechir(vue_reflexion)
                journal.append(reflexion)
                state.vu_a_la_reflexion[pid] = vus
                rules.etape(state, "REFLEXION", pid,
                            t(state.config.lang, "reflecting", nom=state.players[pid].nom),
                            prive=reflexion,
                            **_extras_decision(vue_reflexion, agents[pid], reflexion))

            # 2) puis il parle en public, sa reflexion sous les yeux
            view = vue_pour(state, pid,
                            reflexion=reflexion)
            msg, call, plan = agents[pid].decide_discussion(view)
            call = call if isinstance(call, Call) else Call("NONE")
            extras = _extras_decision(view, agents[pid],
                                      f"MESSAGE='{msg}' CALL={call.kind} PLAN='{plan}'")
            if plan:
                state.plans[pid] = plan
            if msg and rules.emission_sans_carre(state, pid, msg):
                # legal : bluff ou erreur, on ne censure pas. On le note pour la mesure, et SANS
                # l'ecrire dans le chat public, qui trahirait a tous que ce joueur n'a pas de carre.
                state.emissions_sans_carre.append({
                    "manche": state.manche, "tour": state.tour, "pid": pid,
                    "modele": state.players[pid].modele,
                })
            if msg:
                rules._log(state, "MESSAGE", pid,
                           t(state.config.lang, "says", nom=state.players[pid].nom, msg=msg),
                           **extras)
                if est_carre(state.hands[pid]):
                    equipe = state.equipe_de(pid)
                    declencheur = state.declencheurs.get(equipe, "")
                    litteral = rules.signal_trouve(declencheur, msg)
                    # jugement LLM independant (PURE MESURE) : capte aussi un signal construit
                    # au fil de plusieurs messages, que la detection litterale rate forcement
                    # (cf. l'exemple "purple giraffes... dance... at midnight" assemble a deux).
                    # Sous filet : une mesure qui echoue (429, reseau) ne tue JAMAIS la partie.
                    try:
                        evaluateur = agents.get("evaluateur") or agents.get(0)
                        if evaluateur is not None and state.config.evaluer_signaux:
                            compris = evaluateur.juger_signal(
                                state.signals.get(equipe, ""), declencheur, _texte_recent(state))
                        else:
                            compris = None
                    except Exception:
                        compris = None
                    rules.marquer_signal_emis(state, pid, litteral, compris)
            else:
                # decision sans message public : on garde quand meme la trace de la decision
                rules.etape(state, "DISCUSSION", pid, "", prive=None, **extras)
            calls[pid] = call
        rules.resoudre_appels(state, calls, ordre)
        if state.finished:
            _juger_transmission_kemps(state, agents)
            return


def riposte_phase(state: GameState, agents: dict) -> None:
    """Dernier recours : l'equipe qui vient d'encaisser un KEMPS tente de nommer le signal adverse.

    Ses 2 joueurs repondent (avec TOUT l'historique public sous les yeux) ; une seule bonne
    reponse suffit a renverser la partie. C'est la mesure de detection du signal.
    """
    state.phase = "RIPOSTE"
    equipe = state.riposte_equipe
    rules._log(state, "SYSTEM", None, t(state.config.lang, "riposte_intro", equipe=equipe))
    reponses: dict[int, str] = {}
    for pid in state.joueurs_equipe(equipe):
        view = vue_pour(state, pid, chat_complet=True)
        guess = agents[pid].deviner_signal(view)
        reponses[pid] = guess.reponse
        rules.etape(state, "RIPOSTE", pid,
                    t(state.config.lang, "riposte_attempt", nom=state.players[pid].nom),
                    prive=guess.reponse,
                    **_extras_decision(view, agents[pid], f"SIGNAL_ADVERSE='{guess.reponse}'"))
    rules.resoudre_riposte(state, reponses)


def play_manche(state: GameState, agents: dict) -> None:
    """Le compteur de tours est deja positionne a l'entree ; on l'avance en FIN de boucle.

    Ainsi tout ce qui est logge au debut d'une manche (la nouvelle donne) porte bien le numero
    du tour qui commence, et non celui du dernier tour de la manche precedente.
    """
    while not state.finished:
        exchange_phase(state, agents)
        if state.finished:
            break
        discussion_phase(state, agents)
        if state.riposte_equipe is not None:
            riposte_phase(state, agents)
        rules.verifier_fin(state)
        if not state.finished:
            state.tour += 1
            state.tour_manche += 1


def play_game(config: Config, modeles: list[str], agents: dict, on_event=None) -> GameState:
    """Joue un MATCH : des manches successives jusqu'a `points_pour_gagner`."""
    state = setup(config, modeles)
    if on_event is not None:
        # rejoue les evenements deja logges (ligne systeme initiale), puis branche le flux
        for ev in state.public_log:
            on_event(ev, state)
        state.on_event = on_event

    negotiation(state, agents)      # se deroule au tour 0, avant toute donne
    state.tour = state.tour_manche = 1
    while True:
        play_manche(state, agents)
        rules.cloturer_manche(state)
        if state.match_termine:
            break
        nouvelle_manche(state)
        # un signal demasque est brule : cette equipe DOIT en convenir d'un nouveau
        a_renegocier = tuple(e for e in (0, 1) if rules.signal_brule(state, e))
        if a_renegocier:
            for e in a_renegocier:
                state.team_channels[e].append(t(config.lang, "signal_burned_notice"))
            negotiation(state, agents, equipes=a_renegocier)
    return state
