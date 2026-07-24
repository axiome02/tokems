from __future__ import annotations

import random
import time

import requests

PLAFOND_ATTENTE = 60.0     # s : au-dela, c'est un quota epuise, pas une limite de debit


import threading


class APITracker(threading.local):
    def __init__(self):
        self.state = None
        self.publieur = None
        self.current_pid = None


api_tracker = APITracker()


class QuotaError(RuntimeError):
    """L'API refuse durablement (429/403 persistant) : reessayer ne sert a rien."""


def post_json(url: str, headers: dict, payload: dict, *, retries: int = 6,
              timeout: int = 60, pause: float = 0.5, nom: str = "LLM") -> dict:
    """POST JSON avec backoff exponentiel, respect de Retry-After sur 429/5xx.

    Le CORPS de la reponse d'erreur est conserve et remonte : c'est la seule facon de
    distinguer une limite de debit (« reessaie dans 20 s ») d'un quota epuise (« reviens
    demain »), et les deux arrivent en HTTP 429.
    """
    last = None

    if api_tracker.state is not None and api_tracker.current_pid is not None:
        if not hasattr(api_tracker.state, "api_status"):
            api_tracker.state.api_status = {}
        api_tracker.state.api_status[str(api_tracker.current_pid)] = {
            "status": "calling",
            "message": f"Calling {nom}...",
            "last_update": time.time()
        }
        if api_tracker.publieur:
            api_tracker.publieur.ecrire(api_tracker.state, en_cours=True)

    for attempt in range(retries):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                detail = (r.text or "").strip()[:300]
                last = f"HTTP {r.status_code} — {detail or 'pas de detail'}"
                if attempt == retries - 1:
                    break
                # Retry-After fait foi ; sinon backoff exponentiel + jitter
                wait = float(r.headers.get("Retry-After", 2 ** attempt))
                wait_time = min(wait, PLAFOND_ATTENTE)

                if api_tracker.state is not None and api_tracker.current_pid is not None:
                    api_tracker.state.api_status[str(api_tracker.current_pid)] = {
                        "status": "rate_limited",
                        "message": f"Rate limit ({r.status_code}). Retry in {wait_time:.1f}s...",
                        "last_update": time.time(),
                        "retry_after": wait_time
                    }
                    if api_tracker.publieur:
                        api_tracker.publieur.ecrire(api_tracker.state, en_cours=True)

                time.sleep(wait_time + random.uniform(0, 0.5))
                continue
            r.raise_for_status()
            if pause:
                time.sleep(pause)  # courtoisie envers les tiers gratuits

            if api_tracker.state is not None and api_tracker.current_pid is not None:
                api_tracker.state.api_status[str(api_tracker.current_pid)] = {
                    "status": "idle",
                    "message": "Idle",
                    "last_update": time.time()
                }
                if api_tracker.publieur:
                    api_tracker.publieur.ecrire(api_tracker.state, en_cours=True)

            return r.json()
        except requests.RequestException as e:
            last = str(e)

            if api_tracker.state is not None and api_tracker.current_pid is not None:
                api_tracker.state.api_status[str(api_tracker.current_pid)] = {
                    "status": "network_error",
                    "message": "Network error. Retrying...",
                    "last_update": time.time()
                }
                if api_tracker.publieur:
                    api_tracker.publieur.ecrire(api_tracker.state, en_cours=True)

            if attempt < retries - 1:
                time.sleep(min(2 ** attempt, PLAFOND_ATTENTE))

    if api_tracker.state is not None and api_tracker.current_pid is not None:
        api_tracker.state.api_status[str(api_tracker.current_pid)] = {
            "status": "error",
            "message": f"Error: {last[:30]}",
            "last_update": time.time()
        }
        if api_tracker.publieur:
            api_tracker.publieur.ecrire(api_tracker.state, en_cours=True)

    if last and "429" in last:
        raise QuotaError(
            f"{nom}: rate limit or quota reached after {retries} attempts.\n"
            f"  API detail: {last}\n"
            f"  Options: wait a few minutes, fall back to --model mistral-small-latest "
            f"(much larger quotas), or increase --pause to slow down calls."
        )
    raise RuntimeError(f"{nom} call failed after {retries} attempts: {last}")
