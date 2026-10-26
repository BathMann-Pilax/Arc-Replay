"""Recadrage du capteur réglé depuis la télécommande.

Le serveur garde, pour chaque caméra, un zoom et le centre de la zone à garder
(fractions de l'image complète). Le nœud les lit régulièrement et règle la zone
lue sur le capteur (contrôle libcamera « ScalerCrop ») : l'image envoyée est
déjà recadrée, sans perte de définition tant que le capteur a assez de pixels.

Ce module ne dépend pas de picamera2, pour pouvoir être testé sur un PC.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request

log = logging.getLogger("arc.recadrage")


def rectangle(maxi: tuple[int, int, int, int], ratio: float, zoom: float, x: float, y: float
              ) -> tuple[int, int, int, int]:
    """Zone du capteur à lire, au format libcamera (x, y, largeur, hauteur).

    `maxi` : zone maximale du capteur (ScalerCropMaximum).
    `ratio` : largeur / hauteur de l'image envoyée ; la zone garde ce ratio
    pour que l'image ne soit pas déformée.
    `zoom` ≥ 1, `x` et `y` : centre voulu, de 0 à 1.
    """
    x0, y0, lm, hm = maxi
    # Plus grande zone au bon ratio dans le capteur, puis réduite par le zoom
    base_l = min(lm, hm * ratio)
    base_h = base_l / ratio
    zoom = max(1.0, zoom)
    larg, haut = base_l / zoom, base_h / zoom
    cx = x0 + x * lm
    cy = y0 + y * hm
    gauche = min(max(cx - larg / 2, x0), x0 + lm - larg)
    haute = min(max(cy - haut / 2, y0), y0 + hm - haut)
    # Valeurs paires : certains capteurs refusent les coordonnées impaires
    pair = lambda v: int(v) // 2 * 2  # noqa: E731
    return pair(gauche), pair(haute), pair(larg), pair(haut)


def lire(serveur: str, chemin: str, delai_s: float = 2) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://{serveur}/api/recadrage/{chemin}", timeout=delai_s) as r:
            return json.loads(r.read())
    except (OSError, ValueError):
        return None


def suivre(picam, serveur: str, chemin: str, largeur: int, hauteur: int, periode_s: float = 0.5) -> threading.Thread:
    """Applique le recadrage du serveur dès qu'il change (fil en arrière-plan)."""
    maxi = picam.camera_properties.get("ScalerCropMaximum") or picam.camera_controls["ScalerCrop"][1]

    def boucle() -> None:
        dernier = None
        while True:
            r = lire(serveur, chemin)
            if r and r != dernier:
                zone = rectangle(tuple(maxi), largeur / hauteur, r.get("zoom", 1), r.get("x", 0.5), r.get("y", 0.5))
                try:
                    picam.set_controls({"ScalerCrop": zone})
                    log.info("recadrage ×%.2f, zone capteur %s", r.get("zoom", 1), zone)
                    dernier = r
                except Exception as e:  # caméra en cours d'arrêt
                    log.warning("recadrage impossible : %s", e)
            time.sleep(periode_s)

    fil = threading.Thread(target=boucle, daemon=True, name="recadrage")
    fil.start()
    return fil
