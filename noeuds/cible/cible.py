#!/usr/bin/env python3
"""Nœud cible Arc Replay.

Deux modes, choisis par `detection` dans cible.yml :

- `detection: false` (« cible directe ») : vue de la cible en direct, cadrée
  depuis la télécommande, sans OpenCV ni analyse d'image (vue_cadree.py).
  Convient à un Pi 3 B+ qui fait aussi serveur.
- `detection: true` : en plus du flux, garde les dernières images basse
  définition et, à chaque flèche annoncée par le serveur, compare l'image
  d'avant le lâcher et celle d'après, localise la nouvelle flèche et envoie
  l'impact au serveur.

    python3 cible.py --config cible.yml
"""

from __future__ import annotations

import argparse
import base64
import collections
import json
import logging
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import yaml

# streamer.py vit dans noeuds/camera (ou à côté de ce fichier une fois installé)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "camera"))
from streamer import demarrer_flux, flux_actif  # noqa: E402

# OpenCV n'est chargé qu'en mode détection (absent sur un nœud « cible directe »)
detection = None

log = logging.getLogger("arc.cible")


class TamponImages:
    """Les dernières secondes d'images basse définition, horodatées."""

    def __init__(self, duree_s: float = 20):
        self.duree_s = duree_s
        self.images: collections.deque = collections.deque()
        self.verrou = threading.Lock()

    def ajouter(self, horodatage: float, image) -> None:
        with self.verrou:
            self.images.append((horodatage, image))
            while self.images and horodatage - self.images[0][0] > self.duree_s:
                self.images.popleft()

    def avant(self, horodatage: float):
        with self.verrou:
            candidates = [img for t, img in self.images if t <= horodatage]
        return candidates[-1] if candidates else None

    def derniere(self):
        with self.verrou:
            return self.images[-1][1] if self.images else None


def envoyer_impact(serveur: str, corps: dict) -> None:
    requete = urllib.request.Request(
        f"http://{serveur}/api/impact",
        data=json.dumps(corps).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(requete, timeout=10) as r:
        r.read()


class NoeudCible:
    def __init__(self, conf: dict):
        self.conf = conf
        self.tampon = TamponImages()
        calib = json.loads(Path(conf["calibration"]).read_text())
        self.diametre = float(calib["diametre_mm"])
        self.h = detection.homographie([tuple(p) for p in calib["points"]], self.diametre)
        largeur, hauteur = conf["lores"]
        self.masque = detection.masque_blason(self.h, (hauteur, largeur), self.diametre)
        self.connues: set[str] = set()
        self.premier_etat = True

    # --- capture ----------------------------------------------------------

    def boucle_capture(self, picam) -> None:
        largeur, hauteur = self.conf["lores"]
        periode = 1 / self.conf.get("analyse_fps", 4)
        while True:
            debut = time.time()
            yuv = picam.capture_array("lores")
            self.tampon.ajouter(time.time(), yuv[:hauteur, :largeur].copy())
            time.sleep(max(0, periode - (time.time() - debut)))

    # --- analyse d'une flèche --------------------------------------------------

    def analyser(self, fleche: dict) -> None:
        heure = datetime.fromisoformat(fleche["heure"]).timestamp()
        attente = heure + self.conf.get("attente_apres_lacher_s", 2.5) - time.time()
        if attente > 0:
            time.sleep(attente)
        avant = self.tampon.avant(heure - 0.3)
        apres = self.tampon.derniere()
        if avant is None or apres is None:
            log.warning("%s : pas d'image avant le lâcher", fleche["id"])
            return
        d = detection.detecter(
            avant, apres, self.masque,
            extremite=self.conf.get("extremite", "haut"),
            seuil=self.conf.get("seuil", 30),
            aire_min=self.conf.get("aire_min", 30),
        )
        if d is None:
            log.info("%s : aucune flèche détectée dans le blason", fleche["id"])
            return
        x_mm, y_mm = detection.vers_mm(self.h, d.point)
        image = detection.annoter(apres, self.h, self.diametre, d)
        envoyer_impact(self.conf["serveur"], {
            "fleche_id": fleche["id"],
            "x_mm": round(x_mm, 1),
            "y_mm": round(y_mm, 1),
            "diametre_mm": self.diametre,
            "image_jpeg_b64": base64.b64encode(image).decode(),
        })
        log.info("%s : impact à (%.0f, %.0f) mm", fleche["id"], x_mm, y_mm)

    # --- écoute du serveur -----------------------------------------------------

    def traiter_etat(self, etat: dict) -> None:
        for f in etat.get("fleches", []):
            if f["id"] in self.connues:
                continue
            self.connues.add(f["id"])
            # Au démarrage, on n'analyse pas les flèches déjà tirées
            if not self.premier_etat and f.get("impact") is None:
                threading.Thread(target=self.analyser_sans_erreur, args=(f,), daemon=True).start()
        if etat.get("fleche") == 0 and not etat.get("fleches"):
            self.connues.clear()  # nouvelle séance
        self.premier_etat = False

    def analyser_sans_erreur(self, fleche: dict) -> None:
        try:
            self.analyser(fleche)
        except Exception as e:
            log.error("%s : analyse impossible : %s", fleche["id"], e)

    def boucle_serveur(self) -> None:
        from websockets.sync.client import connect

        while True:
            try:
                with connect(f"ws://{self.conf['serveur']}/api/ws", open_timeout=5) as ws:
                    log.info("connecté au serveur %s", self.conf["serveur"])
                    self.premier_etat = True
                    for message in ws:
                        m = json.loads(message)
                        if m.get("type") == "etat":
                            self.traiter_etat(m["etat"])
            except Exception as e:
                log.warning("serveur injoignable (%s), nouvel essai dans 3 s", e)
                time.sleep(3)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default=str(Path(__file__).with_name("cible.yml")))
    conf = yaml.safe_load(Path(p.parse_args().config).read_text())

    if not conf.get("detection", True):
        import vue_cadree

        return vue_cadree.executer({
            "serveur": conf["serveur"], "chemin": conf.get("chemin", "cible"),
            "capteur": conf.get("capteur"), "largeur": conf.get("largeur"), "hauteur": conf.get("hauteur"),
            "fps": conf.get("fps"), "debit": conf.get("debit"), "cadrage": conf.get("cadrage"),
            "fichier_cadrage": conf.get("fichier_cadrage"),
        })

    global detection
    import detection as module_detection

    detection = module_detection
    noeud = NoeudCible(conf)
    picam, sortie = demarrer_flux(
        conf["serveur"], conf.get("chemin", "cible"),
        conf.get("largeur", 1920), conf.get("hauteur", 1080), conf.get("fps", 30),
        conf.get("debit", 6_000_000), lores=tuple(conf["lores"]),
        zoom=conf.get("zoom_numerique"),
    )
    threading.Thread(target=noeud.boucle_capture, args=(picam,), daemon=True).start()
    threading.Thread(target=noeud.boucle_serveur, daemon=True).start()
    while flux_actif(sortie):
        time.sleep(1)
    log.error("publication vidéo interrompue, arrêt (systemd relancera)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
