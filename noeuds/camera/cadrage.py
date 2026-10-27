"""Cadrage numérique d'une caméra Raspberry Pi, réglé depuis la télécommande.

Le cadrage est une zone du capteur au format de l'image envoyée (16:9 par
défaut), définie par son centre et un zoom :

- zoom 1 : la plus grande zone 16:9 du capteur ;
- zoom 8 (`zoom_max`) : une zone 8 fois plus étroite ;
- chaque appui sur « zoom + » multiplie le zoom par `pas_zoom` (1,25) ;
- chaque flèche déplace la zone de `pas_deplacement` (10 %) de sa largeur visible ;
- la zone reste toujours dans le capteur.

La zone est appliquée au capteur (contrôle libcamera « ScalerCrop ») : l'image
envoyée est déjà recadrée, sans redémarrer le flux ni réencoder.

Ce module ne dépend pas de picamera2, pour être testé sur un PC.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger("arc.cadrage")

Rectangle = tuple[int, int, int, int]  # x, y, largeur, hauteur (pixels du capteur)


@dataclass
class Reglages:
    zoom_max: float = 8.0
    pas_zoom: float = 1.25
    pas_deplacement: float = 0.10
    ratio: float = 16 / 9  # largeur / hauteur de l'image envoyée

    @classmethod
    def depuis(cls, d: Optional[dict], ratio: Optional[float] = None) -> "Reglages":
        d = d or {}
        r = cls(
            zoom_max=max(1.0, float(d.get("zoom_max", cls.zoom_max))),
            pas_zoom=max(1.01, float(d.get("pas_zoom", cls.pas_zoom))),
            pas_deplacement=min(1.0, max(0.01, float(d.get("pas_deplacement", cls.pas_deplacement)))),
        )
        if ratio:
            r.ratio = ratio
        return r


def zone_maximale(picam) -> Rectangle:
    """Zone maximale du capteur, à lire APRÈS picam.configure().

    Avant la configuration, picamera2 renvoie (0, 0, 0, 0) : on se rabat alors
    sur la taille du capteur.
    """
    candidats = [picam.camera_properties.get("ScalerCropMaximum")]
    try:
        candidats.append(picam.camera_controls["ScalerCrop"][1])  # (min, max, défaut)
    except (AttributeError, KeyError, IndexError, TypeError):
        pass
    for zone in candidats:
        try:
            x, y, l, h = (int(v) for v in zone)
        except (TypeError, ValueError):
            continue
        if l > 0 and h > 0:
            return x, y, l, h
    l, h = picam.sensor_resolution
    return 0, 0, int(l), int(h)


class Cadrage:
    def __init__(self, maxi: Rectangle, reglages: Reglages = Reglages(),
                 cx: float = 0.5, cy: float = 0.5, zoom: float = 1.0):
        self.maxi = tuple(int(v) for v in maxi)
        self.reglages = reglages
        self.cx, self.cy, self.zoom = float(cx), float(cy), float(zoom)
        self._borner()

    # --- géométrie ---------------------------------------------------------------

    def _base(self) -> tuple[float, float]:
        """Plus grande zone au bon format dans le capteur (zoom 1)."""
        _, _, lm, hm = self.maxi
        larg = min(lm, hm * self.reglages.ratio)
        return larg, larg / self.reglages.ratio

    def taille(self) -> tuple[float, float]:
        larg, haut = self._base()
        return larg / self.zoom, haut / self.zoom

    def _borner(self) -> None:
        self.zoom = min(self.reglages.zoom_max, max(1.0, self.zoom))
        _, _, lm, hm = self.maxi
        larg, haut = self.taille()
        demi_x, demi_y = larg / 2 / lm, haut / 2 / hm
        self.cx = min(1 - demi_x, max(demi_x, self.cx))
        self.cy = min(1 - demi_y, max(demi_y, self.cy))

    def rectangle(self) -> Rectangle:
        """Zone du capteur pour ScalerCrop, en pixels pairs (exigé par l'ISP)."""
        x0, y0, lm, hm = self.maxi
        larg, haut = self.taille()
        l = max(2, int(larg) // 2 * 2)
        h = max(2, int(haut) // 2 * 2)
        x = int(x0 + self.cx * lm - l / 2) // 2 * 2
        y = int(y0 + self.cy * hm - h / 2) // 2 * 2
        x = min(max(x, x0), x0 + lm - l)
        y = min(max(y, y0), y0 + hm - h)
        return x, y, l, h

    # --- commandes -----------------------------------------------------------------

    def deplacer(self, dx: float = 0, dy: float = 0) -> None:
        """Déplace de dx, dy pas (un pas = `pas_deplacement` de la largeur visible)."""
        _, _, lm, hm = self.maxi
        pas_px = self.reglages.pas_deplacement * self.taille()[0]
        self.cx += float(dx) * pas_px / lm
        self.cy += float(dy) * pas_px / hm
        self._borner()

    def zoomer(self, pas: Optional[float] = None, facteur: Optional[float] = None) -> None:
        """`pas` = +1 (zoom +) ou -1 (zoom −) ; ou un `facteur` multiplicatif."""
        if facteur is None:
            facteur = self.reglages.pas_zoom ** float(pas or 0)
        if facteur > 0:
            self.zoom *= float(facteur)
        # Évite les 0,99999 après plusieurs « + » puis « − »
        self.zoom = round(self.zoom, 4)
        self._borner()

    def reinitialiser(self) -> None:
        self.cx = self.cy = 0.5
        self.zoom = 1.0
        self._borner()

    def appliquer(self, commande: dict) -> None:
        """Commande reçue du serveur : {"action": "deplacer"|"zoomer"|"reinitialiser", ...}."""
        action = commande.get("action")
        if action == "deplacer":
            self.deplacer(commande.get("dx", 0), commande.get("dy", 0))
        elif action == "zoomer":
            self.zoomer(commande.get("pas"), commande.get("facteur"))
        elif action == "reinitialiser":
            self.reinitialiser()
        elif action != "lire":
            raise ValueError(f"action de cadrage inconnue : {action!r}")

    # --- état et persistance ---------------------------------------------------------

    def etat(self) -> dict:
        """Cadrage effectif, renvoyé au serveur après chaque commande."""
        return {
            "cx": round(self.cx, 4),
            "cy": round(self.cy, 4),
            "zoom": round(self.zoom, 4),
            "zoom_max": self.reglages.zoom_max,
            "pas_zoom": self.reglages.pas_zoom,
            "rectangle": list(self.rectangle()),
            "capteur": list(self.maxi),
        }

    def sauver(self, fichier: Path) -> None:
        """Écriture atomique : un arrêt brutal ne laisse pas un fichier à moitié écrit."""
        fichier = Path(fichier)
        fichier.parent.mkdir(parents=True, exist_ok=True)
        temporaire = fichier.with_name(fichier.name + ".tmp")
        temporaire.write_text(json.dumps({"cx": self.cx, "cy": self.cy, "zoom": self.zoom}))
        os.replace(temporaire, fichier)

    @classmethod
    def charger(cls, fichier: Path, maxi: Rectangle, reglages: Reglages = Reglages()) -> "Cadrage":
        """Cadrage enregistré, ou vue complète si le fichier manque ou est illisible."""
        try:
            d = json.loads(Path(fichier).read_text())
            return cls(maxi, reglages, d.get("cx", 0.5), d.get("cy", 0.5), d.get("zoom", 1.0))
        except (OSError, ValueError, TypeError, AttributeError):
            return cls(maxi, reglages)
