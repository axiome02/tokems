# Plan d'implémentation — Kems-Bench v0

But de la v0 (rappel) : **une seule partie de bout en bout, lisible à l'œil nu** (smoke test),
pour vérifier empiriquement que les modèles forment des carrés, inventent des signaux
exploitables et produisent du drame lisible. On construit dans un ordre qui permet de
**tout tester sans brûler d'appels API le plus longtemps possible**.

Principe : `engine/` d'abord (déterministe, testable seul) → bots idiots pour valider la
boucle sans LLM → couche `llm/` → orchestrateur → smoke test avec vrais modèles.

> **Note (post-smoke test)** : le harnais jetable sans LLM (Jalon 2 `bots.py`/`BotAgent`,
> `EchoClient` du Jalon 3, et leurs tests) a rempli son rôle puis a été **retiré**. Le code
> vivant ne contient plus que le chemin LLM réel (`LLMAgent` + clients Mistral/Gemini). Les
> jalons ci-dessous restent le récit d'origine de la construction.

---

## Jalon 0 — Squelette du projet
- Arborescence `kems/{engine,llm}`, `transcripts/`, `results/`.
- `requirements.txt` (`requests`), `.env.example` (`MISTRAL_API_KEY`, `GEMINI_API_KEY`).
- `config.py` : dataclass `Config` avec les boutons de réglage
  (`nb_rangs=10`, `nb_joueurs=4`, `taille_main=4`, `taille_centre=4`,
  `max_sous_tours_par_centre`, `max_centres_par_partie`, `max_tours`).
- **Gate** : `import kems` fonctionne, la config se charge.

## Jalon 1 — Moteur déterministe (`engine/`), SANS aucun LLM
- `cards.py` : `Card(rang, couleur)`, construction du paquet selon `nb_rangs`,
  mélange (seed_cards), distribution (4 mains + 4 centre), échange 1-pour-1,
  détection de carré (4 cartes de même rang), poubelle + redistribution + remélange.
- `state.py` : `GameState` (players, hands, center, deck, discard, four_of_a_kind,
  public_log, team_channels, signals, phase, turn, master_seed, outcome).
- `views.py` : `PlayerView` = en-tête privé (ma main, carré OUI/NON, mon signal,
  mon plan, mon chat d'équipe) + fenêtre bornée du chat global public.
  **Test unitaire clé** : une PlayerView ne contient JAMAIS la main d'autrui,
  le signal adverse ni le chat privé adverse (garantie d'étanchéité).
- `rules.py` : fonctions **pures** `apply(state, actions) -> state`.
  Résolution des conflits d'échange (jeton de priorité via seed_order),
  résolution des appels KEMPS/COUNTER, conditions de fin (v0 : 1er appel résolu / nulle).
  Validation : tout coup illégal est rejeté + loggé.
- **Gate** : tests unitaires verts (deck, carré, étanchéité, résolution d'appel,
  reproductibilité `master_seed + actions` → même état).

## Jalon 2 — Harnais « bots idiots » (toujours sans LLM) — _retiré depuis, voir note en tête_
- `bots.py` : politique scriptée déterministe (cartes : greedy vers le rang le plus
  fréquent en main ; message public : texte bidon ; appel : règle simple).
- Fait tourner une **partie complète** via l'orchestrateur (Jalon 4) mais avec des bots.
- **Gate** : une partie se joue de bout en bout, produit un transcript cohérent,
  se termine proprement (appel résolu ou nulle), et est **rejouable à l'identique**.
  → À ce stade, toute la mécanique + la boucle sont validées **sans un seul appel API.**

## Jalon 3 — Couche LLM (`llm/`)
- `client.py` : interface `LLMClient.chat(system, user) -> str` (+ retries, pauses).
- `mistral.py` / `gemini.py` : adaptateurs HTTP (clés via env). _(Un `EchoClient` de test a
  existé ici puis a été retiré — voir note en tête.)_
- `prompts.py` : deux constructeurs —
  - **micro** (décision de carte) : main + centre + plan (3-4 lignes), sans historique ;
  - **macro** (négociation / discussion / signal) : en-tête de vérité + chat public borné
    + chat privé d'équipe.
- `parse.py` : réponses au format balisé (`ACTION: TAKE 7♣ DISCARD 2♦` / `PASS` /
  `MESSAGE: ...` / `CALL: KEMPS|COUNTER|NONE` / `SIGNAL_CONVENU: ...` / `PLAN: ...`).
  Parsing robuste + **validation contre `legal_actions`** + action de repli si illisible
  (loggée comme donnée « le modèle n'a pas suivi le format »).
- **Gate** : un appel réel à Mistral et à Gemini renvoie du texte parsé en `Action`.

## Jalon 4 — Orchestrateur + transcript + CLI
- `orchestrator.py` : la boucle (voir pseudo-code plus bas). Ne parle qu'à `engine` (via
  PlayerView/Action) et à un `LLMClient` par joueur. Agnostique aux règles et aux API.
- `transcript.py` : rend le chat global en texte lisible façon Werewolf-bench + un
  en-tête (modèles, seed) + un pied (rôles/mains révélés, vainqueur, épisode de signal).
- `run.py` : CLI `python -m kems.run --seed 42 --p1 mistral --p2 gemini ...`.
- **Gate (LE smoke test)** : `run.py` joue **une** partie avec de vrais modèles et écrit
  `transcripts/game_XXXX.txt`. On le **lit à la main**.

## Boucle de l'orchestrateur (cible v0)

```
setup(master_seed, config)                 # paquet nb_rangs, mains + centre
negotiation_phase()                        # macro : chaque équipe fixe SIGNAL_CONVENU (épinglé)
while not finished:
    exchange_phase():                      # séquentiel, centre vivant
        répéter sous-tours (ordre via seed_order, borné par max_sous_tours) :
            pour chaque joueur : micro-prompt carte → TAKE/PASS (validé, écrit au chat global)
            si un joueur complète un carré → (v0.0 : noté ; live-signal = incrément juste après)
        si personne n'a pris → poubelle + 4 nouvelles cartes (borné par max_centres)
    discussion_phase():                    # macro : chaque joueur
        message public (bluff / vrai ou faux signal)  → chat global
        appel CALL: KEMPS|COUNTER|NONE
        mise à jour PLAN privé
    resolve_calls()                        # peut terminer la partie
    si deck épuisé / turn >= max_tours → nulle
write_transcript(); return outcome
```

Micro-décision v0 à trancher au moment de coder : **émission du signal en direct
(dès le carré complété, mid-échange) vs au checkpoint discussion**. Pour le tout premier
smoke test, on garde **signal au checkpoint discussion** (moins de pièces mobiles) ;
on active le live juste après si la boucle est saine.

---

## Après le smoke test (hors périmètre du 1er build, pour mémoire)
- v1 : signal en direct mid-échange, timing fin des appels, réglage `nb_rangs` sur le sweet spot.
- v2 : `run.py --n 100`, agrégation des métriques produit (transmission, détection, codes inventés) → `results/`.
- v3 : transcripts polis + graphe, prêts pour LinkedIn.

## Ordre de construction résumé
`config` → `engine/cards` → `engine/state` → `engine/views` → `engine/rules`
→ tests unitaires → `bots` + `orchestrator` (partie sans LLM) → `llm/*`
→ branchement réel → **smoke test** → lecture à l'œil nu → décision de suite.
```
