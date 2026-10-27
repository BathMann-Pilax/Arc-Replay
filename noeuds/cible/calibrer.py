#!/usr/bin/env python3
"""Calibration du nœud cible, à refaire si la caméra ou le blason bouge.

1. Arrêter le service :           sudo systemctl stop arc-replay-cible
2. Prendre une image :            python3 calibrer.py capture --sortie blason.jpg
3. Ouvrir blason.jpg et relever les pixels du bord EXTÉRIEUR du blason :
   point le plus haut, le plus à droite, le plus bas, le plus à gauche.
4. Enregistrer :
   python3 calibrer.py points --diametre 1220 --image blason.jpg \\
       320,40 600,250 318,460 42,248
   -> écrit calibration.json et verification.jpg (zones projetées sur l'image).
5. Vérifier que les cercles de verification.jpg tombent sur les zones du blason,
   puis relancer le service : sudo systemctl start arc-replay-cible
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import yaml

# streamer.py vit dans noeuds/camera (ou à côté de ce fichier une fois installé)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "camera"))
import detection  # noqa: E402
from streamer import recadrage_zoom  # noqa: E402


def capture(conf: dict, sortie: Path) -> None:
    from picamera2 import Picamera2

    largeur, hauteur = conf["lores"]
    picam = Picamera2()
    controles: dict = {}
    recadrage = recadrage_zoom(picam, conf.get("zoom_numerique"))
    if recadrage:
        controles["ScalerCrop"] = recadrage  # même cadrage que le service
    picam.configure(picam.create_still_configuration(
        main={"size": (conf.get("largeur", 1920), conf.get("hauteur", 1080))},
        lores={"size": (largeur, hauteur), "format": "YUV420"},
        controls=controles,
    ))
    picam.start()
    import time
    time.sleep(2)  # laisse l'exposition se stabiliser
    image = picam.capture_array("lores")[:hauteur, :largeur]
    picam.close()
    cv2.imwrite(str(sortie), image)
    print(f"Image enregistrée : {sortie} ({largeur}x{hauteur})")


def enregistrer_points(conf: dict, diametre: float, points: list[str], image: Path | None) -> None:
    pts = []
    for p in points:
        x, y = (float(v) for v in p.split(","))
        pts.append((x, y))
    h = detection.homographie(pts, diametre)  # lève une erreur si les points sont incohérents
    cible = Path(conf["calibration"])
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(json.dumps({"diametre_mm": diametre, "points": pts}, indent=2))
    print(f"Calibration enregistrée : {cible}")
    if image:
        gris = cv2.imread(str(image), cv2.IMREAD_GRAYSCALE)
        verif = image.with_name("verification.jpg")
        verif.write_bytes(detection.annoter(gris, h, diametre, None))
        print(f"Vérification : {verif}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default=str(Path(__file__).with_name("cible.yml")))
    sous = p.add_subparsers(dest="commande", required=True)
    c = sous.add_parser("capture", help="prendre une image de référence")
    c.add_argument("--sortie", type=Path, default=Path("blason.jpg"))
    pt = sous.add_parser("points", help="enregistrer les 4 points du bord du blason")
    pt.add_argument("--diametre", type=float, required=True, help="diamètre du blason en mm (400, 600, 800, 1220)")
    pt.add_argument("--image", type=Path, help="image de capture, pour générer verification.jpg")
    pt.add_argument("points", nargs=4, help="x,y du haut, de la droite, du bas, de la gauche")
    args = p.parse_args()
    conf = yaml.safe_load(Path(args.config).read_text())

    if args.commande == "capture":
        capture(conf, args.sortie)
    else:
        enregistrer_points(conf, args.diametre, args.points, args.image)
    return 0


if __name__ == "__main__":
    sys.exit(main())
