from __future__ import annotations

import random
import time

import requests

PLAFOND_ATTENTE = 60.0     # s : au-dela, c'est un quota epuise, pas une limite de debit


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
    for attempt in range(retries):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                detail = (r.text or "").strip()[:300]
                last = f"HTTP {r.status_code} — {detail or 'pas de detail'}"
                if attempt == retries - 1:
                    break
                # Retry-After fait foi ; sinon backoff exponentiel + jitter (evite que les
                # 4 joueurs, synchronises, retapent l'API exactement en meme temps).
                wait = float(r.headers.get("Retry-After", 2 ** attempt))
                time.sleep(min(wait, PLAFOND_ATTENTE) + random.uniform(0, 0.5))
                continue
            r.raise_for_status()
            if pause:
                time.sleep(pause)  # courtoisie envers les tiers gratuits
            return r.json()
        except requests.RequestException as e:
            last = str(e)
            if attempt < retries - 1:
                time.sleep(min(2 ** attempt, PLAFOND_ATTENTE))
    if last and "429" in last:
        raise QuotaError(
            f"{nom}: rate limit or quota reached after {retries} attempts.\n"
            f"  API detail: {last}\n"
            f"  Options: wait a few minutes, fall back to --model mistral-small-latest "
            f"(much larger quotas), or increase --pause to slow down calls."
        )
    raise RuntimeError(f"{nom} call failed after {retries} attempts: {last}")
