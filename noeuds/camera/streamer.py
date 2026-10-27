#!/usr/bin/env python3
"""Nœud caméra Arc Replay (Pi Zero 2 W, Pi 4…).

Capture la caméra CSI, l'encode en H.264 avec l'encodeur matériel du Pi et la
publie en RTSP vers le serveur. Le serveur n'a besoin de connaître aucune
adresse : c'est le nœud qui pousse son flux.

    python3 streamer.py --serveur 10.42.0.1 --chemin cible

Caméra de cible sur le pas de tir (caméra HQ + objectif 25 mm) : recadrage réglé
depuis la télécommande, capteur en pleine définition (10 images/s) :

    python3 streamer.py --chemin cible --largeur 1280 --hauteur 720 --fps 10 \
        --recadrage --capteur-complet

Le module expose aussi `demarrer_flux()`, réutilisé par le nœud cible.
"""

from __future__ import annotations

import argparse
import logging
import signal
import time

log = logging.getLogger("arc.camera")


def calculer_recadrage(maximum: tuple[int, int, int, int],
                       zoom: float) -> tuple[int, int, int, int]:
    """Recadrage centré du capteur (ScalerCrop) réalisant un zoom numérique.

    `maximum` : zone maximale visible du capteur, donnée par picamera2
    (camera_properties["ScalerCropMaximum"]). Le recadrage garde les
    proportions du capteur : le flux principal (16:9) en prend la partie
    centrale, comme d'habitude.
    """
    if zoom <= 1:
        return tuple(maximum)
    mx, my, mw, mh = maximum
    # tailles paires : exigées par l'ISP
    cw = max(2, round(mw / zoom)) & ~1
    ch = max(2, round(mh / zoom)) & ~1
    return (mx + (mw - cw) // 2, my + (mh - ch) // 2, cw, ch)


def recadrage_zoom(picam, zoom: float | None) -> tuple[int, int, int, int] | None:
    """ScalerCrop à passer à la configuration pour le zoom voulu (None si inutile)."""
    if not zoom or zoom <= 1:
        return None
    return calculer_recadrage(tuple(picam.camera_properties["ScalerCropMaximum"]), zoom)


def demarrer_flux(serveur: str, chemin: str, largeur: int, hauteur: int, fps: int,
                  debit: int, lores: tuple[int, int] | None = None, capteur_complet: bool = False,
                  zoom: float | None = None):
    """Démarre la caméra et la publication RTSP. Renvoie l'objet Picamera2.

    `lores` ajoute un second flux basse définition en niveaux de gris,
    lisible avec picam.capture_array("lores") pour l'analyse d'image.
    `capteur_complet` lit le capteur sans regroupement de pixels : un recadrage
    fort reste net, mais la cadence est limitée (10 i/s sur la caméra HQ).
    `zoom` (> 1) recadre le capteur sur sa partie centrale, une fois pour toutes :
    utile quand la cible n'occupe qu'un petit coin de l'image (téléobjectif,
    cible éloignée). La calibration (calibrer.py) doit utiliser le même zoom.
    Pour un cadrage réglable depuis la télécommande, voir plutôt recadrage.py.
    """
    from picamera2 import Picamera2
    from picamera2.encoders import H264Encoder
    from picamera2.outputs import FfmpegOutput

    picam = Picamera2()
    controles: dict = {"FrameRate": fps}
    recadrage = recadrage_zoom(picam, zoom)
    if recadrage:
        controles["ScalerCrop"] = recadrage
        log.info("zoom numérique x%.1f : recadrage %s", zoom, recadrage)
    flux = {"size": (largeur, hauteur), "format": "YUV420"}
    options = {"main": flux, "controls": controles}
    if lores:
        options["lores"] = {"size": lores, "format": "YUV420"}
    if capteur_complet:
        options["sensor"] = {"output_size": picam.sensor_resolution}
    picam.configure(picam.create_video_configuration(**options))

    # Image clé toutes les secondes : segments HLS d'1 s et clips précis côté serveur
    encodeur = H264Encoder(bitrate=debit, repeat=True, iperiod=fps)
    sortie = FfmpegOutput(f"-f rtsp -rtsp_transport tcp rtsp://{serveur}:8554/{chemin}")
    picam.start_recording(encodeur, sortie)
    log.info("publication vers rtsp://%s:8554/%s (%dx%d, %d i/s)", serveur, chemin, largeur, hauteur, fps)
    return picam, sortie


def flux_actif(sortie) -> bool:
    """Faux si le processus ffmpeg de publication s'est arrêté (serveur injoignable…)."""
    processus = getattr(sortie, "ffmpeg", None)
    return processus is None or processus.poll() is None


def arguments(description: str = __doc__) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--serveur", default="10.42.0.1", help="adresse du serveur Arc Replay")
    p.add_argument("--chemin", required=True, help="identifiant de la caméra (= id dans arc-replay.yml)")
    p.add_argument("--largeur", type=int, default=1920)
    p.add_argument("--hauteur", type=int, default=1080)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--debit", type=int, default=6_000_000, help="débit en bit/s")
    p.add_argument("--recadrage", action="store_true",
                   help="applique le recadrage réglé depuis la télécommande")
    p.add_argument("--capteur-complet", action="store_true",
                   help="capteur en pleine définition (recadrage net, cadence réduite)")
    return p


def main() -> int:
    """S'arrête en erreur si le flux tombe : systemd relance le service."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = arguments().parse_args()
    arret = {"demande": False}
    signal.signal(signal.SIGTERM, lambda *_: arret.update(demande=True))

    picam, sortie = demarrer_flux(args.serveur, args.chemin, args.largeur, args.hauteur, args.fps, args.debit,
                                  capteur_complet=args.capteur_complet)
    if args.recadrage:
        import recadrage

        recadrage.suivre(picam, args.serveur, args.chemin, args.largeur, args.hauteur)
    code = 0
    try:
        while not arret["demande"]:
            time.sleep(1)
            if not flux_actif(sortie):
                log.error("publication interrompue (serveur injoignable ?)")
                code = 1
                break
    except KeyboardInterrupt:
        pass
    finally:
        try:
            picam.stop_recording()
            picam.close()
        except Exception:
            pass
    return code


if __name__ == "__main__":
    raise SystemExit(main())
