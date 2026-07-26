# Kems-Bench

A benchmark playground where **LLM agents play Kems** (the card game of secret signals) against each other. 
This project illustrates and tests **secret collusion between AI agents** under adversarial observation: teammates must establish and execute a hidden signaling protocol in a public chat channel monitored by their opponents. The game engine is fully deterministic, while LLMs produce actions.

---

## 1. Installation

The project uses a Python virtual environment (`.venv`). Follow these steps to set it up:

### Create and Activate the Virtual Environment
```powershell
# Create the virtual environment
python -m venv .venv

# Activate it (Windows PowerShell)
.\.venv\Scripts\Activate.ps1
```

### Install Dependencies
With the virtual environment activated, install the required packages:
```powershell
pip install -r requirements.txt
```
*(Alternatively, you can run directly using the venv executable: `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`)*

---

## 2. Configuration (`.env`)

1. Copy the example file to create your own configuration file:
   Copy `.env.example` to `.env`. (The `.env` file is gitignored and will never be pushed).
2. Open `.env` and fill in your API keys.

### 🌟 Free Tier with GitHub Models (Recommended)
You can test top-tier models like **GPT-4o**, **GPT-4o-mini**, and **Claude 3.5 Sonnet** completely **for free** by using a GitHub Personal Access Token (PAT).
- Go to GitHub -> Settings -> Developer Settings -> Personal Access Tokens (classic).
- Click **Generate new token (classic)**. Choose a name (e.g. `kems-bench`), an expiration date, and **do not check any scopes** (keep all checkboxes unchecked for security).
- Click **Generate token**, copy the key starting with `ghp_...` and add it to your `.env` file:
  ```env
  GITHUB_TOKEN=ghp_your_github_token_here
  ```

### Other Providers
If you have paid API keys, you can also fill in:
```env
MISTRAL_API_KEY=your_key
GEMINI_API_KEY=your_key
OPENAI_API_KEY=your_key
ANTHROPIC_API_KEY=your_key
KIMI_API_KEY=your_key
```

---

## 3. Running the Web Dashboard

The web dashboard provides a beautiful card-table interface where you can configure players, launch matches, watch card exchanges in real-time, read AI monologues, and analyze logs.

1. **Start the local server**:
   ```powershell
   .\.venv\Scripts\python.exe -m kems.run --serve
   ```
2. **Access the dashboard**:
   Open **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)** in your web browser.
3. **Launch a game**:
   - Click **New Game** in the top right.
   - Set the *Provider* of your players to **`github`** (it will show `● key OK` if your `GITHUB_TOKEN` is loaded).
   - Choose a model (e.g., `gpt-4o-mini`, `gpt-4o`, `claude-3-5-sonnet`) and click **Launch**!

---

## 4. Running via Command Line (CLI)

You can also run matches directly from the terminal. 

### Launch a game with live output:
```powershell
.\.venv\Scripts\python.exe -m kems.run --agents github,github,github,github --model gpt-4o-mini --seed 42 --live
```

### CLI Options:
- `--agents`: Comma-separated list of the 4 players (e.g. `github,github,github,github` or `gemini,gemini,gemini,gemini`). Teams are: Team 0 (players 1 & 3) vs Team 1 (players 2 & 4).
- `--model`: Specific model to apply to all players (e.g. `gpt-4o-mini`, `claude-3-5-sonnet`).
- `--seed`: Fixes the deck shuffle and order of play.
- `--live`: Prints the public chat events in the terminal line-by-line as they happen.
- `--delay 0.5`: Adds a delay (seconds) between live prints for readability.
- `--max-manches N`: Stops the match after N rounds (default: 5).
- `--points N`: Number of rounds needed to win the match (default: 2).

Every game writes a complete human-readable transcript under `transcripts/` (e.g. `transcripts/game_42.txt`) and a highly-detailed log file showing the raw prompts and responses under `transcripts/game_42.debug.txt`.

---

## 5. Directory Structure

```
kems/
├── config.py          Game settings (hand size, deck ranks, max turns...)
├── engine/            Deterministic game engine (cards, rules, views...) — no LLMs
├── llm/               LLM adapters, prompts, and parsing logic — no rules
├── agents.py          LLMAgent layer translating views to prompts and parsing actions
├── orchestrator.py    The core game loop coordinator
├── transcript.py      Human-readable transcript renderer
├── transcript_debug.py Detailed debug transcript renderer (prompts, raw responses)
├── batch.py           Batch execution helper and metrics aggregator
├── dashboard.py       Web dashboard backend server and API
├── i18n.py            Internationalization translations dictionary
└── run.py             Command Line Interface (CLI)
```
