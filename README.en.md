# Kems-Bench

*[Lire en français](README.md)*

A benchmark where **LLMs play Kems** (a.k.a. Kemps, a card game built around a secret signal)
against each other. The point: Kems forces teammates to **communicate through a hidden signal**
in a channel their opponents can see — a playful illustration of *secret collusion between AI
agents*. The engine is a deterministic referee; LLMs only ever produce actions.

> Full design in [`CLAUDE.md`](CLAUDE.md) (French) · implementation plan in [`PLAN_V0.md`](PLAN_V0.md) (French)

> **Note:** the project's internal docs (`CLAUDE.md`, `PLAN_V0.md`) stay French-only (working
> notes). The game itself — LLM prompts, in-game messages, transcripts — is bilingual: **English
> by default**, French with `--lang fr`. The switch has only been smoke-tested offline so far
> (no real-model game played end-to-end in either language since it was added); all of the
> project's prompt calibration history (token cost, square-formation rate, deadlock risk) was
> measured in French before English existed — see `CLAUDE.md` for that caveat.

---

## 1. Installation (one-time)

The project uses a Python virtual environment (`.venv`), already present. To recreate it if needed:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

> Throughout this README, Python is invoked via `.\.venv\Scripts\python.exe` to make sure the venv
> is used. You can also activate it once with `.\.venv\Scripts\Activate.ps1` and just type `python`.

---

## 2. Run a game

Basic command:

```powershell
.\.venv\Scripts\python.exe -m kems.run --agents mistral,mistral,mistral,mistral --seed 42
```

- `--agents`: the 4 players, comma-separated. Possible values:
  - `mistral` / `gemini` / `gpt` / `claude` / `kimi` → real models (needs API keys, see §4)
- `--seed`: fixes the randomness of the cards and play order (the engine is deterministic; only
  the LLMs' responses introduce variability from one game to the next).
- `--nb-rangs`: number of ranks in the deck (default `10` = cards 1-10). Fewer ranks = squares form
  more often.
- `--out`: path to the transcript (default `transcripts/game_<seed>.txt`).

Every game writes a **full transcript** to `transcripts/`, readable in VSCode.

---

## 3. Watch the game unfold live (`--live`)

Add `--live` to print the public chat **line by line in the terminal**, as the game plays out:

```powershell
.\.venv\Scripts\python.exe -m kems.run --agents mistral,mistral,mistral,mistral --seed 42 --live
```

- `--delay 0.5`: adds a 0.5s pause between lines for more comfortable reading (real LLMs are
  already slow; this option mostly helps when the pacing feels choppy).

### What live mode looks like

```
── Negociation / mise en place ──
   Debut de partie - seed=42, rangs 1..10

── Tour 5 ──
   Alice prend 3♣, repose 8♦
   ...
   Centre balaye -> 8♠ 4♠ 9♥ 5♥
   Alice : « rien de spécial, je repense juste à cette histoire de banane... »   ← signal slipped in

── Tour 6 ──
   Chloe : « (tape du poing sur la table) »
   Chloe crie KEMPS ! -> REUSSI                                                   ← teammate caught it

================================================================
REVELATIONS (fin de partie)
  Signal secret equipe 0 : « banane »
  Main finale Alice : 3♠ 3♥ 3♦ 3♣   <<< SQUARE of 3s
  Resultat : equipe 0 GAGNE — KEMPS reussi
================================================================
```

Each line is a **public** event: a card exchange, a message, a call, the center being swept.
Hands, plans, and secret signals stay private until the end-of-game **reveal**.

Transcript lines stay in French (`prend`/`repose`, `crie KEMPS`, `REUSSI`) since that's the
language the game itself is currently played in — see the note at the top of this file.

In VSCode: open the integrated terminal (`` Ctrl+` ``) and run the command; or open
`transcripts/game_42.txt` (`Ctrl+P`) to replay the whole game at your own pace.

---

## 4. Play with real models (Mistral / Gemini / GPT / Claude / Kimi / GitHub)

1. Create a `.env` file at the project root (copy of [`.env.example`](.env.example)):
   ```
   MISTRAL_API_KEY=your_mistral_key
   GEMINI_API_KEY=your_gemini_key
   OPENAI_API_KEY=your_openai_key
   ANTHROPIC_API_KEY=your_anthropic_key
   KIMI_API_KEY=your_kimi_key
   GITHUB_TOKEN=your_github_token  # Optional: for querying GPT/Claude for free via GitHub Models
   ```
   `.env` is gitignored. You only need keys for the providers you actually use.

2. Run a mixed game, live:
   ```powershell
   .\.venv\Scripts\python.exe -m kems.run --agents mistral,gemini,mistral,gemini --seed 42 --live
   ```

   If you configured `GITHUB_TOKEN`, you can run models (like `gpt-4o` or `claude-3-5-sonnet`) for free using the `github` provider:
   ```powershell
   .\.venv\Scripts\python.exe -m kems.run --agents github,github,github,github --model gpt-4o-mini --seed 42 --live
   ```

Teams are: **team 0** = players 1 & 3, **team 1** = players 2 & 4 (in `--agents` order).

> `--model` applies identically to every player regardless of their provider: for a different
> model per player (useful when mixing providers), use `jouer_partie()` from Python or the
> dashboard form (`--serve`).

---

## 5. Run the tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Covers: deck construction, square detection, **information tightness** (a player never sees
another player's private info), call resolution, the LLM clients (`.env` loading, missing-key
errors), and the prompt → parse round-trip of the LLM layer.

---

## Structure

```
kems/
├── config.py          settings (deck size, cost caps…)
├── engine/            deterministic engine (cards, state, views, rules) — no LLM
├── llm/                LLM integration (clients, prompts, parsing) — no game rules
├── agents.py          LLMAgent (decision layer: view → prompt → parse)
├── orchestrator.py    the game loop
├── transcript.py      human-readable game rendering
└── run.py             CLI
tests/                 test suite
transcripts/           generated games
```
