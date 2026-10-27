#!/usr/bin/env python3
"""Test de la détection d'impact avec la caméra cible face au blason
(Pi 3 B+ + HQ Camera au pas de tir), sans serveur Arc Replay.

À placer dans noeuds/cible/ (à côté de detection.py), puis, dans l'ordre :

  1. python3 test_impact.py apercu
       -> apercu.jpg : champ complet avec une grille tous les 10 %
  2. python3 test_impact.py cadrer --crop X,Y,L,H
       -> blason.jpg : zone recadrée (fractions du capteur, lues sur la grille)
  3. python3 test_impact.py points HX,HY DX,DY BX,BY GX,GY --diametre 400
       -> verification.jpg : bord du blason en haut, à droite, en bas, à gauche
  4. python3 test_impact.py test [--decalage DX,DY] [--seuil 30]
       -> une ligne et une image annotée (fleche_NN.jpg) par flèche
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from picamera2 import Picamera2

sys.path.insert(0, str(Path(__file__).resolve().parent))
import detection  # noqa: E402

REGLAGE = Path("reglage.json")


def charger() -> dict:
    if not REGLAGE.exists():
        sys.exit("reglage.json absent : lance d'abord « cadrer ».")
    return json.loads(REGLAGE.read_text())


def sauver(reglage: dict) -> None:
    REGLAGE.write_text(json.dumps(reglage, indent=2))


class Camera:
    """Capture en niveaux de gris d'une zone du capteur, en mode pleine définition."""

    def __init__(self, crop=(0.0, 0.0, 1.0, 1.0), largeur_max=1600):
        self.cam = Picamera2()
        # ScalerCropMaximum peut valoir (0, 0, 0, 0) tant que la caméra n'est pas
        # configurée : on se rabat alors sur la taille du capteur (4056x3040).
        mx, my, mw, mh = self.cam.camera_properties.get("ScalerCropMaximum", (0, 0, 0, 0))
        if mw <= 0 or mh <= 0:
            mx, my = 0, 0
            mw, mh = self.cam.sensor_resolution
        fx, fy, fw, fh = crop
        zone = (int(mx + fx * mw), int(my + fy * mh), int(fw * mw), int(fh * mh))
        largeur, hauteur = zone[2], zone[3]
        if largeur > largeur_max:
            hauteur = int(hauteur * largeur_max / largeur)
            largeur = largeur_max
        config = self.cam.create_still_configuration(
            main={"size": (largeur // 2 * 2, hauteur // 2 * 2), "format": "RGB888"},
            sensor={"output_size": self.cam.sensor_resolution},  # 4056x3040, pas le mode binné
            buffer_count=1,
            controls={"ScalerCrop": zone},
        )
        self.cam.configure(config)
        self.cam.start()
        time.sleep(2)
        # On fige exposition et balance des blancs : sinon chaque variation
        # automatique apparaît comme une « différence » entre deux images.
        meta = self.cam.capture_metadata()
        self.cam.set_controls({
            "AeEnable": False,
            "AwbEnable": False,
            "ExposureTime": meta["ExposureTime"],
            "AnalogueGain": meta["AnalogueGain"],
            "ColourGains": meta["ColourGains"],
        })
        time.sleep(1)

    def gris(self, n=3) -> np.ndarray:
        """Moyenne de n images pour réduire le bruit."""
        images = [
            cv2.cvtColor(self.cam.capture_array("main"), cv2.COLOR_BGR2GRAY).astype(np.float32)
            for _ in range(n)
        ]
        return np.mean(images, axis=0).astype(np.uint8)


def score(r_mm: float, diametre: float, rayon_fleche: float) -> int:
    """Zone touchée ; une flèche qui touche une ligne compte la zone supérieure."""
    rayon = diametre / 2
    d = max(r_mm - rayon_fleche, 0.0)
    if d >= rayon:
        return 0
    return 10 - int(d // (rayon / 10))


def cmd_apercu(_args):
    cam = Camera(largeur_max=2028)
    img = cv2.cvtColor(cam.gris(n=1), cv2.COLOR_GRAY2BGR)
    h, w = img.shape[:2]
    jaune = (0, 255, 255)
    for i in range(1, 10):
        x, y = w * i // 10, h * i // 10
        cv2.line(img, (x, 0), (x, h), jaune, 1)
        cv2.line(img, (0, y), (w, y), jaune, 1)
        cv2.putText(img, f"{i / 10:.1f}", (x + 4, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, jaune, 2)
        cv2.putText(img, f"{i / 10:.1f}", (4, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.9, jaune, 2)
    cv2.imwrite("apercu.jpg", img)
    print("apercu.jpg écrit. Repère la butte sur la grille, puis :")
    print("  python3 test_impact.py cadrer --crop X,Y,L,H   (ex. 0.40,0.35,0.20,0.20)")


def cmd_cadrer(args):
    crop = [float(v) for v in args.crop.split(",")]
    if len(crop) != 4 or not all(0 <= v <= 1 for v in crop):
        sys.exit("--crop attend 4 fractions entre 0 et 1 : X,Y,LARGEUR,HAUTEUR")
    cam = Camera(crop)
    cv2.imwrite("blason.jpg", cam.gris())
    reglage = json.loads(REGLAGE.read_text()) if REGLAGE.exists() else {}
    reglage["crop"] = crop
    reglage.pop("points", None)  # nouveau cadrage : la calibration est à refaire
    sauver(reglage)
    print("blason.jpg écrit. Relève les pixels du bord EXTÉRIEUR du blason")
    print("(haut, droite, bas, gauche), puis lance « points ».")


def cmd_points(args):
    reglage = charger()
    points = [tuple(float(v) for v in p.split(",")) for p in args.points]
    h = detection.homographie(points, args.diametre)
    reglage.update(points=points, diametre=args.diametre)
    sauver(reglage)
    img = cv2.imread("blason.jpg", cv2.IMREAD_GRAYSCALE)
    Path("verification.jpg").write_bytes(detection.annoter(img, h, args.diametre, None))
    print("verification.jpg écrit : les cercles doivent tomber sur les zones du blason.")


def cmd_test(args):
    reglage = charger()
    if "points" not in reglage:
        sys.exit("Calibration manquante : lance « points ».")
    diametre = reglage["diametre"]
    dx, dy = (float(v) for v in args.decalage.split(","))
    cam = Camera(reglage["crop"])
    h = detection.homographie(reglage["points"], diametre)
    px_mm = detection.px_par_mm(h, diametre)
    premiere = cam.gris()
    masque = detection.masque_blason(h, premiere.shape, diametre)

    # Toutes les images sont recalées sur celle de la calibration : si le
    # blason bouge un peu, les zones restent à leur place.
    reference = cv2.imread("blason.jpg", cv2.IMREAD_GRAYSCALE)
    if reference is None or reference.shape != premiere.shape:
        reference = premiere

    def capturer():
        image, deplacement = detection.aligner(reference, cam.gris(), masque)
        if deplacement > 3:
            print(f"  (blason décalé de {deplacement:.0f} px par rapport à la calibration, recalé)")
        if deplacement > 40:
            print("  Décalage important : refais « cadrer » puis « points ».")
        return image

    avant = capturer()
    print(f"Échelle : {px_mm:.2f} px/mm. Référence prise.")
    print("  Entrée       : après chaque flèche")
    print("  r + Entrée   : nouvelle référence (après avoir retiré les flèches)")
    print("  q + Entrée   : quitter")
    n = 0
    while True:
        reponse = input("> ").strip().lower()
        if reponse == "q":
            break
        apres = capturer()
        if reponse == "r":
            avant = apres
            print("Nouvelle référence.")
            continue
        n += 1
        det = detection.detecter_face(avant, apres, masque, px_mm, seuil=args.seuil / 100,
                                      aire_min_mm2=args.aire_min, point=args.point)
        if det is None:
            print(f"Flèche {n} : rien détecté (essaie un --seuil plus bas)")
        else:
            # Point d'entrée de la flèche (bout fin, opposé à l'empennage) ;
            # --decalage corrige un éventuel écart constant.
            x, y = detection.vers_mm(h, det.point)
            x, y = x + dx, y + dy
            r = math.hypot(x, y)
            print(f"Flèche {n} : x={x:+.0f} mm  y={y:+.0f} mm  à {r:.0f} mm du centre"
                  f"  ->  {score(r, diametre, args.rayon_fleche)}   (zone de {det.aire:.0f} px)")
            if not det.fiable:
                print("  ! tube peu visible (vue de bout, ou tube foncé sur zone foncée) :"
                      " position approximative")
        Path(f"fleche_{n:02d}.jpg").write_bytes(detection.annoter(apres, h, diametre, det))
        avant = apres


def main():
    p = argparse.ArgumentParser(description="Test de détection d'impact, caméra face au blason")
    sous = p.add_subparsers(dest="commande", required=True)

    sous.add_parser("apercu", help="champ complet avec grille")

    c = sous.add_parser("cadrer", help="recadrer sur la butte")
    c.add_argument("--crop", required=True, help="X,Y,LARGEUR,HAUTEUR en fractions du capteur")

    c = sous.add_parser("points", help="calibrer sur le bord du blason")
    c.add_argument("points", nargs=4, help="HX,HY DX,DY BX,BY GX,GY (pixels de blason.jpg)")
    c.add_argument("--diametre", type=float, default=400, help="diamètre du blason en mm")

    c = sous.add_parser("test", help="détecter les flèches une à une")
    c.add_argument("--decalage", default="0,0", help="correction de parallaxe DX,DY en mm")
    c.add_argument("--seuil", type=int, default=30, help="contraste minimal en %% (plus bas = plus sensible)")
    c.add_argument("--aire-min", type=float, default=20, help="taille minimale d'une zone, en mm²")
    c.add_argument("--point", default="auto",
                   choices=["auto", "centre", "haut", "bas", "gauche", "droite"],
                   help="auto = pointe du tube ; centre = centre de la zone (gommettes)")
    c.add_argument("--rayon-fleche", type=float, default=4.5, help="rayon du tube en mm")

    args = p.parse_args()
    {"apercu": cmd_apercu, "cadrer": cmd_cadrer, "points": cmd_points, "test": cmd_test}[args.commande](args)


if __name__ == "__main__":
    main()
