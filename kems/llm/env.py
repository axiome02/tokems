from __future__ import annotations

import os
from pathlib import Path


def load_env(path: str = ".env") -> None:
    """Charge un fichier .env (KEY=VALUE) dans os.environ, sans ecraser les vraies variables."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), val)
