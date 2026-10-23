"""Détection du lâcher au micro.

Le claquement de la corde est un son bref et fort : on surveille le niveau
sonore par blocs de 10 ms et on signale un lâcher au serveur dès que le niveau
dépasse le seuil, avec l'heure exacte du bloc.

Variables d'environnement :
    ARC_SERVEUR         http://backend:8000
    SEUIL_DB            -20   (dBFS ; plus bas = plus sensible)
    PERIPHERIQUE_AUDIO  nom ou numéro du micro (vide = micro par défaut)
    ANTI_REBOND_S       2
    MODE_REGLAGE        1 pour afficher le niveau en continu et régler le seuil
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
import urllib.request
from datetime import datetime, timezone

import numpy as np

log = logging.getLogger("arc.lacher")


def niveau_dbfs(bloc: np.ndarray) -> float:
    """Niveau crête d'un bloc audio float32 (-1..1), en dBFS."""
    crete = float(np.max(np.abs(bloc))) if bloc.size else 0.0
    return 20 * np.log10(max(crete, 1e-6))


class Detecteur:
    def __init__(self, seuil_db: float, anti_rebond_s: float):
        self.seuil_db = seuil_db
        self.anti_rebond_s = anti_rebond_s
        self.dernier = -1e9

    def bloc(self, niveau: float, horodatage: float) -> bool:
        """Vrai si ce bloc correspond à un nouveau lâcher."""
        if niveau >= self.seuil_db and horodatage - self.dernier >= self.anti_rebond_s:
            self.dernier = horodatage
            return True
        return False


def signaler(serveur: str, horodatage: float) -> None:
    corps = {
        "heure": datetime.fromtimestamp(horodatage, timezone.utc).isoformat(),
        "source": "audio",
    }
    requete = urllib.request.Request(
        f"{serveur}/api/lacher", data=json.dumps(corps).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(requete, timeout=5) as r:
        log.info("lâcher signalé : %s", r.read().decode()[:120])


def main() -> None:
    import sounddevice as sd

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    serveur = os.environ.get("ARC_SERVEUR", "http://backend:8000")
    seuil = float(os.environ.get("SEUIL_DB", "-20"))
    reglage = os.environ.get("MODE_REGLAGE") == "1"
    peripherique = os.environ.get("PERIPHERIQUE_AUDIO") or None
    if peripherique and peripherique.isdigit():
        peripherique = int(peripherique)
    detecteur = Detecteur(seuil, float(os.environ.get("ANTI_REBOND_S", "2")))
    envois: queue.Queue[float] = queue.Queue()

    def expediteur() -> None:
        while True:
            t = envois.get()
            try:
                signaler(serveur, t)
            except OSError as e:
                log.error("serveur injoignable : %s", e)

    threading.Thread(target=expediteur, daemon=True).start()

    frequence = 48000
    taille_bloc = frequence // 100  # 10 ms
    dernier_affichage = 0.0
    maxi = -120.0

    def rappel(donnees, nb_images, infos_temps, statut):
        nonlocal dernier_affichage, maxi
        maintenant = time.time()
        # Heure du début du bloc (le rappel arrive un peu après la capture)
        horodatage = maintenant - nb_images / frequence
        niveau = niveau_dbfs(donnees[:, 0])
        if detecteur.bloc(niveau, horodatage):
            envois.put(horodatage)
        if reglage:
            maxi = max(maxi, niveau)
            if maintenant - dernier_affichage > 0.5:
                print(f"niveau max sur 0,5 s : {maxi:6.1f} dBFS (seuil {seuil})", flush=True)
                dernier_affichage, maxi = maintenant, -120.0

    log.info("écoute du micro %s, seuil %.0f dBFS", peripherique or "par défaut", seuil)
    with sd.InputStream(device=peripherique, channels=1, samplerate=frequence,
                        blocksize=taille_bloc, dtype="float32", callback=rappel):
        while True:
            time.sleep(1)


if __name__ == "__main__":
    main()
