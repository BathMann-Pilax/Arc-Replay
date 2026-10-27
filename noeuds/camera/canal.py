"""Canal de commande entre un nœud Raspberry Pi et le serveur.

Le nœud ouvre lui-même une connexion WebSocket vers le serveur : le serveur
n'a besoin de connaître l'adresse d'aucun nœud.

    ws://<serveur>/api/noeud/ws?camera=<id>

Messages du serveur vers le nœud :
    {"type": "config", "camera": {...}}                 à la connexion et après « Recharger »
    {"type": "commande", "id": 7, "commande": {...}}    ex. {"action": "zoomer", "pas": 1}
Messages du nœud vers le serveur :
    {"type": "cadrage", "cadrage": {...}}               cadrage effectif (à la connexion)
    {"type": "reponse", "id": 7, "cadrage": {...}}      ou {"type": "reponse", "id": 7, "erreur": "..."}

Nécessite python3-websockets (version 11 ou plus, pour le client synchrone).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Callable, Optional
from urllib.parse import quote

log = logging.getLogger("arc.canal")


def repondre(traiter: Optional[Callable[[dict], dict]], message: dict) -> Optional[dict]:
    """Réponse à un message « commande » (None pour les autres messages)."""
    if message.get("type") != "commande":
        return None
    reponse = {"type": "reponse", "id": message.get("id")}
    if traiter is None:
        reponse["erreur"] = "caméra pas encore démarrée"
        return reponse
    try:
        reponse["cadrage"] = traiter(message.get("commande") or {})
    except Exception as e:  # commande invalide, caméra en cours d'arrêt…
        reponse["erreur"] = str(e)
    return reponse


class Canal:
    def __init__(self, serveur: str, camera: str):
        self.url = f"ws://{serveur}/api/noeud/ws?camera={quote(camera)}"
        self.config: Optional[dict] = None
        self.config_recue = threading.Event()
        self.traiter: Optional[Callable[[dict], dict]] = None  # commande -> cadrage effectif
        self.sur_config: Optional[Callable[[dict], None]] = None
        self._etat: Optional[dict] = None
        self._ws = None
        self._verrou = threading.Lock()

    def demarrer(self) -> "Canal":
        threading.Thread(target=self._boucle, daemon=True, name="canal").start()
        return self

    def attendre_config(self, delai_s: float) -> Optional[dict]:
        self.config_recue.wait(delai_s)
        return self.config

    def annoncer(self, cadrage: dict) -> None:
        """Cadrage effectif : envoyé maintenant et à chaque reconnexion."""
        self._etat = cadrage
        self._envoyer({"type": "cadrage", "cadrage": cadrage})

    # --- interne -------------------------------------------------------------------

    def _envoyer(self, message: dict) -> None:
        with self._verrou:
            if self._ws is None:
                return
            try:
                self._ws.send(json.dumps(message))
            except Exception as e:
                log.warning("envoi impossible : %s", e)

    def _recevoir(self, message: dict) -> None:
        if message.get("type") == "config":
            premiere = self.config is None
            self.config = message.get("camera") or {}
            self.config_recue.set()
            if not premiere and self.sur_config:
                self.sur_config(self.config)
            return
        reponse = repondre(self.traiter, message)
        if reponse is not None:
            if reponse.get("cadrage"):
                self._etat = reponse["cadrage"]
            self._envoyer(reponse)

    def _boucle(self) -> None:
        from websockets.sync.client import connect

        while True:
            try:
                with connect(self.url, open_timeout=5) as ws:
                    with self._verrou:
                        self._ws = ws
                    log.info("connecté au serveur (%s)", self.url)
                    if self._etat:
                        self._envoyer({"type": "cadrage", "cadrage": self._etat})
                    for brut in ws:
                        self._recevoir(json.loads(brut))
            except Exception as e:
                log.warning("serveur injoignable (%s), nouvel essai dans 3 s", e)
            finally:
                with self._verrou:
                    self._ws = None
            time.sleep(3)
