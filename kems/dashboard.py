"""Dashboard quasi-direct : publie l'etat de la partie en JSON, servi en local.

Le moteur reste l'unique source de verite ; ce module ne fait que PROJETER son etat vers un
fichier que la page web relit en boucle. Il n'influence jamais le jeu.
"""
from __future__ import annotations

import functools
import http.server
import json
import os
import threading
import time
from datetime import datetime

from .engine.cards import est_carre
from .engine.state import GameState

DOSSIER = "dashboard"
FICHIER = "state.json"
FICHIER_TRANSCRIPT = "partie.txt"


def _instantane(state: GameState, tokens: dict | None, en_cours: bool,
                transcript: str | None = None) -> dict:
    """Projette l'etat en dict serialisable. Les secrets sont marques comme tels."""
    return {
        "maj": datetime.now().isoformat(timespec="seconds"),
        "en_cours": en_cours,
        "transcript": transcript,
        "seed": state.config.master_seed,
        "rangs": state.config.nb_rangs,
        "manche": state.manche,
        "tour": state.tour,
        "phase": state.phase,
        "scores": {str(e): n for e, n in state.scores.items()},
        "vainqueur_match": state.vainqueur_match,
        "joueurs": [
            {
                "pid": p.pid, "nom": p.nom, "equipe": p.equipe, "modele": p.modele,
                "carre": est_carre(state.hands.get(p.pid, [])),
            }
            for p in state.players
        ],
        "chat": [
            {"manche": ev.manche, "tour": ev.tour, "type": ev.type,
             "pid": ev.pid, "texte": ev.texte}
            for ev in state.public_log
        ],
        # champs lourds (prompt + reponse brute de chaque decision) : reserves au transcript
        # debug, inutiles a la page et couteux a reecrire 2x/s
        "timeline": [{k: v for k, v in e.items() if k not in ("prompt_user", "reponse_brute")}
                     for e in state.timeline],
        "centre": [str(c) for c in state.center],
        "episodes": list(state.episodes),
        "appels_sans_signal": list(state.appels_sans_signal),
        "emissions_sans_carre": list(state.emissions_sans_carre),
        "manches": list(state.historique_manches),
        "tokens": tokens or {"grand_total": 0, "per_model": {}},
        # PRIVE : jamais vu par les agents, affiche seulement si l'observateur le demande
        "secrets": {
            "signaux": {str(e): s for e, s in state.signals.items()},
            "declencheurs": {str(e): d for e, d in state.declencheurs.items()},
            "mains": {str(p.pid): [str(c) for c in state.hands.get(p.pid, [])]
                      for p in state.players},
            "journaux": {str(pid): list(j) for pid, j in state.journaux.items()},
            "chats_equipe": {str(e): list(c) for e, c in state.team_channels.items()},
        },
    }


class Publieur:
    """Ecrit l'instantane a chaque evenement public. Ecriture atomique (rename)."""

    INTERVALLE = 0.5        # s : l'instantane pese ~150 Ko, inutile de le reecrire plus souvent

    def __init__(self, dossier: str = DOSSIER, tokens=None):
        self.chemin = os.path.join(dossier, FICHIER)
        self._tokens = tokens or (lambda: None)
        self._derniere = 0.0
        self.transcript = None
        os.makedirs(dossier, exist_ok=True)

    def rebrancher(self, tokens) -> None:
        """Chaque partie a ses propres agents : on repointe le compteur de tokens."""
        self._tokens = tokens
        self._derniere = 0.0
        self.transcript = None

    def deposer_transcript(self, texte: str, nom: str) -> None:
        """Copie le recapitulatif a cote de la page pour qu'elle puisse l'offrir en telechargement."""
        chemin = os.path.join(os.path.dirname(self.chemin), FICHIER_TRANSCRIPT)
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(texte)
        self.transcript = nom

    def __call__(self, ev, state: GameState) -> None:
        maintenant = time.monotonic()
        if maintenant - self._derniere < self.INTERVALLE:
            return
        self._derniere = maintenant
        self.ecrire(state, en_cours=True)

    def ecrire(self, state: GameState, en_cours: bool = True) -> None:
        texte = json.dumps(_instantane(state, self._tokens(), en_cours, self.transcript),
                           ensure_ascii=False)
        tmp = self.chemin + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(texte)
        # os.replace est atomique, mais sous Windows il echoue si un autre processus tient le
        # fichier (OneDrive, antivirus, le navigateur). On reessaie, puis on ecrit en direct :
        # une lecture partielle fait juste echouer un JSON.parse, que la page reessaie 1 s plus tard.
        for essai in range(5):
            try:
                os.replace(tmp, self.chemin)
                return
            except PermissionError:
                time.sleep(0.05 * (essai + 1))
        try:
            with open(self.chemin, "w", encoding="utf-8") as f:
                f.write(texte)
            os.remove(tmp)
        except OSError:
            pass                # le dashboard n'est qu'un observateur : il ne doit jamais casser la partie


class Pilote:
    """Lance une partie en tache de fond a la demande du tableau de bord.

    Une seule partie a la fois : deux parties concurrentes ecriraient dans le meme state.json.
    """

    def __init__(self, publieur: "Publieur"):
        self.publieur = publieur
        self.thread: threading.Thread | None = None
        self.erreur: str | None = None

    @property
    def occupe(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def lancer(self, reglages: dict) -> None:
        if self.occupe:
            raise RuntimeError("a game is already running")
        self.erreur = None
        self.thread = threading.Thread(target=self._jouer, args=(reglages,), daemon=True)
        self.thread.start()

    def _jouer(self, reglages: dict) -> None:
        # import tardif : `run` importe ce module, on eviterait sinon un import circulaire
        from .run import jouer_partie
        try:
            jouer_partie(reglages, self.publieur)
        except Exception as e:                     # noqa: BLE001 — remonte tel quel a l'UI
            self.erreur = f"{type(e).__name__} : {e}"


class _Handler(http.server.SimpleHTTPRequestHandler):
    """Fichiers statiques + une mini API pour piloter les parties."""

    pilote: Pilote | None = None

    def log_message(self, *args):
        pass                                       # les logs HTTP noieraient la sortie de la partie

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")   # sinon le navigateur sert un state.json perime
        super().end_headers()

    def _json(self, code: int, charge: dict) -> None:
        corps = json.dumps(charge, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def do_GET(self):
        if self.path.startswith("/api/statut"):
            p = self.pilote
            return self._json(200, {"occupe": bool(p and p.occupe),
                                    "erreur": p.erreur if p else None})
        return super().do_GET()

    def do_POST(self):
        if not self.path.startswith("/api/lancer"):
            return self._json(404, {"erreur": "unknown route"})
        if self.pilote is None:
            return self._json(503, {"erreur": "controller unavailable"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            reglages = json.loads(self.rfile.read(n) or b"{}")
            self.pilote.lancer(reglages)
            return self._json(200, {"ok": True})
        except Exception as e:                     # noqa: BLE001
            return self._json(400, {"erreur": str(e)})


def demarrer_serveur(dossier: str = DOSSIER, port: int = 8000,
                     pilote: Pilote | None = None) -> str:
    """Sert `dossier` en tache de fond et renvoie l'URL. Le thread meurt avec le programme."""
    os.makedirs(dossier, exist_ok=True)
    handler = functools.partial(_Handler, directory=dossier)
    _Handler.pilote = pilote
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{port}/"
