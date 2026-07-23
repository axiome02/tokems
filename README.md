# Kems-Bench

*[Read this in English](README.en.md)*

Un benchmark où des **LLM jouent au Kems** (jeu de cartes à signal secret) les uns contre les
autres. L'intérêt : le Kems oblige les coéquipiers à **communiquer par un signal caché** dans un
canal observé par les adversaires — c'est une illustration ludique de la *collusion secrète entre
agents IA*. Le moteur est un arbitre déterministe ; les LLM ne font que produire des actions.

> Conception détaillée dans [`CLAUDE.md`](CLAUDE.md) · plan d'implémentation dans [`PLAN_V0.md`](PLAN_V0.md)

---

## 1. Installation (une fois)

Le projet utilise un environnement virtuel Python (`.venv`), déjà présent. S'il faut le recréer :

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

> Dans ce README, on appelle Python via `.\.venv\Scripts\python.exe` pour être sûr d'utiliser le
> venv. Tu peux aussi l'activer une fois avec `.\.venv\Scripts\Activate.ps1` puis taper juste `python`.

---

## 2. Lancer une partie

La commande de base :

```powershell
.\.venv\Scripts\python.exe -m kems.run --agents mistral,mistral,mistral,mistral --seed 42
```

- `--agents` : les 4 joueurs, séparés par des virgules. Valeurs possibles :
  - `mistral` / `gemini` / `gpt` / `claude` / `kimi` → vrais modèles (nécessite les clés API, voir §4)
- `--lang` : langue de la partie (prompts LLM + messages en jeu + transcript). `en` (défaut) ou
  `fr`. Aucune mesure de référence n'a encore été refaite en `fr` depuis l'introduction du
  multilingue — voir `CLAUDE.md`.
- `--seed` : fixe l'aléa des cartes et de l'ordre de jeu (le moteur est déterministe ; seules
  les réponses des LLM introduisent de la variabilité d'une partie à l'autre).
- `--nb-rangs` : nombre de rangs du paquet (défaut `10` = cartes 1-10). Moins de rangs = carrés plus fréquents.
- `--out` : chemin du transcript (défaut `transcripts/game_<seed>.txt`).

Chaque partie écrit un **transcript complet** dans `transcripts/`, lisible dans VSCode.

---

## 3. Voir la partie défiler en direct (`--live`)

Ajoute `--live` pour afficher le chat global **ligne par ligne dans le terminal**, au fur et à
mesure du jeu :

```powershell
.\.venv\Scripts\python.exe -m kems.run --agents mistral,mistral,mistral,mistral --seed 42 --live
```

- `--delay 0.5` : ajoute une pause de 0,5 s entre chaque ligne pour lire plus confortablement
  (les vrais LLM sont déjà lents ; l'option est surtout utile si le débit paraît haché).

### À quoi ressemble le mode live

```
── Negociation / mise en place ──
   Debut de partie - seed=42, rangs 1..10

── Tour 5 ──
   Alice prend 3♣, repose 8♦
   ...
   Centre balaye -> 8♠ 4♠ 9♥ 5♥
   Alice : « rien de spécial, je repense juste à cette histoire de banane... »   ← signal glissé

── Tour 6 ──
   Chloe : « (tape du poing sur la table) »
   Chloe crie KEMPS ! -> REUSSI                                                   ← le partenaire a capté

================================================================
REVELATIONS (fin de partie)
  Signal secret equipe 0 : « banane »
  Main finale Alice : 3♠ 3♥ 3♦ 3♣   <<< CARRE de 3
  Resultat : equipe 0 GAGNE — KEMPS reussi
================================================================
```

Chaque ligne est un événement **public** : échange de carte, message, appel, balayage du centre.
Les mains, plans et signaux restent privés jusqu'aux **révélations** de fin de partie.

Dans VSCode : ouvre le terminal intégré (`` Ctrl+` ``) et lance la commande ; ou ouvre le fichier
`transcripts/game_42.txt` (`Ctrl+P`) pour relire toute la partie à ton rythme.

---

## 4. Jouer avec de vrais modèles (Mistral / Gemini / GPT / Claude / Kimi)

1. Crée un fichier `.env` à la racine (copie de [`.env.example`](.env.example)) :
   ```
   MISTRAL_API_KEY=ta_cle_mistral
   GEMINI_API_KEY=ta_cle_gemini
   OPENAI_API_KEY=ta_cle_openai
   ANTHROPIC_API_KEY=ta_cle_anthropic
   KIMI_API_KEY=ta_cle_kimi
   ```
   Le `.env` est ignoré par git. Seules les clés des fournisseurs que tu utilises sont nécessaires.

2. Lance une partie mixte, en direct :
   ```powershell
   .\.venv\Scripts\python.exe -m kems.run --agents mistral,gemini,mistral,gemini --seed 42 --live
   ```

Les équipes sont : **équipe 0** = joueurs 1 & 3, **équipe 1** = joueurs 2 & 4 (dans l'ordre `--agents`).

> `--model` s'applique identiquement à tous les joueurs quel que soit leur fournisseur : pour un
> modèle différent par joueur (utile en mix multi-fournisseurs), passer par `jouer_partie()` en
> Python ou par le formulaire du dashboard (`--serve`).

---

## 5. Lancer les tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Couvre : construction du paquet, détection des carrés, **étanchéité de l'information** (un joueur ne
voit jamais l'info privée d'autrui), résolution des appels, les clients LLM (chargement `.env`,
absence de clé), et le round-trip prompts → parse de la couche LLM.

---

## Structure

```
kems/
├── config.py          réglages (nb de rangs, bornes de coût…)
├── engine/            moteur déterministe (cartes, état, vues, règles) — aucun LLM
├── llm/               intégration LLM (clients, prompts, parsing) — aucune règle
├── agents.py          LLMAgent (couche de décision : vue → prompt → parse)
├── orchestrator.py    la boucle de jeu
├── transcript.py      rendu lisible de la partie
└── run.py             CLI
tests/                 suite de tests
transcripts/           parties générées
```
