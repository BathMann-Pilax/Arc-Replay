"""Détection de la nouvelle flèche sur le blason (fonctions pures, testables sur PC).

Principe :
1. on compare une image prise juste avant le lâcher et une image prise après
   l'arrivée de la flèche : seule la nouvelle flèche a changé ;
2. on garde la plus grande zone de changement à l'intérieur du blason ;
3. le point d'entrée dans le blason est l'extrémité de cette zone située du
   côté configuré (le tube dépasse vers la caméra, donc d'un côté connu) ;
4. une homographie, calibrée une fois sur 4 points du bord du blason,
   convertit ce point en millimètres depuis le centre.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import cv2
import numpy as np

Point = tuple[float, float]
EXTREMITES = ("haut", "bas", "gauche", "droite")


def homographie(points_image: Sequence[Point], diametre_mm: float) -> np.ndarray:
    """Matrice image -> blason (mm, origine au centre, y vers le haut).

    `points_image` : bord extérieur du blason en haut, à droite, en bas, à gauche.
    """
    if len(points_image) != 4:
        raise ValueError("il faut exactement 4 points : haut, droite, bas, gauche")
    r = diametre_mm / 2
    monde = np.float32([(0, r), (r, 0), (0, -r), (-r, 0)])
    return cv2.getPerspectiveTransform(np.float32(points_image), monde)


def vers_mm(h: np.ndarray, point: Point) -> Point:
    x, y = cv2.perspectiveTransform(np.float32([[point]]), h)[0][0]
    return float(x), float(y)


def vers_image(h: np.ndarray, points_mm: np.ndarray) -> np.ndarray:
    inverse = np.linalg.inv(h)
    return cv2.perspectiveTransform(np.float32(points_mm).reshape(-1, 1, 2), inverse).reshape(-1, 2)


def cercle_image(h: np.ndarray, rayon_mm: float, n: int = 72) -> np.ndarray:
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return vers_image(h, np.stack([rayon_mm * np.cos(a), rayon_mm * np.sin(a)], axis=1))


def masque_blason(h: np.ndarray, forme: tuple[int, int], diametre_mm: float, marge: float = 1.05) -> np.ndarray:
    """Masque (uint8) du blason dans l'image : on ignore tout ce qui est autour."""
    masque = np.zeros(forme, np.uint8)
    contour = cercle_image(h, diametre_mm / 2 * marge).astype(np.int32)
    cv2.fillPoly(masque, [contour], 255)
    return masque


@dataclass
class Detection:
    point: Point          # point d'entrée estimé, en pixels
    aire: float           # surface de la zone de changement, en pixels
    contour: np.ndarray


def detecter(
    avant: np.ndarray,
    apres: np.ndarray,
    masque: Optional[np.ndarray] = None,
    extremite: str = "haut",
    seuil: int = 30,
    aire_min: float = 30,
) -> Optional[Detection]:
    """Cherche la nouvelle flèche entre deux images en niveaux de gris."""
    if extremite not in EXTREMITES:
        raise ValueError(f"extremite doit valoir {', '.join(EXTREMITES)}")
    a = cv2.GaussianBlur(avant, (5, 5), 0)
    b = cv2.GaussianBlur(apres, (5, 5), 0)
    diff = cv2.absdiff(a, b)
    # Compense un léger changement global de luminosité (nuage, exposition)
    diff = cv2.subtract(diff, np.full_like(diff, int(np.median(diff))))
    _, binaire = cv2.threshold(diff, seuil, 255, cv2.THRESH_BINARY)
    if masque is not None:
        binaire = cv2.bitwise_and(binaire, masque)
    noyau = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binaire = cv2.morphologyEx(binaire, cv2.MORPH_OPEN, noyau)
    binaire = cv2.morphologyEx(binaire, cv2.MORPH_CLOSE, noyau, iterations=2)

    contours, _ = cv2.findContours(binaire, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    contours = [c for c in contours if cv2.contourArea(c) >= aire_min]
    if not contours:
        return None
    c = max(contours, key=cv2.contourArea)
    pts = c.reshape(-1, 2)
    indice = {
        "haut": pts[:, 1].argmin(),
        "bas": pts[:, 1].argmax(),
        "gauche": pts[:, 0].argmin(),
        "droite": pts[:, 0].argmax(),
    }[extremite]
    x, y = pts[indice]
    return Detection(point=(float(x), float(y)), aire=float(cv2.contourArea(c)), contour=c)


def annoter(image_gris: np.ndarray, h: np.ndarray, diametre_mm: float,
            detection: Optional[Detection]) -> bytes:
    """Image JPEG avec les zones du blason projetées et l'impact détecté."""
    img = cv2.cvtColor(image_gris, cv2.COLOR_GRAY2BGR)
    for zone in range(10):
        rayon = diametre_mm / 2 * (10 - zone) / 10
        cv2.polylines(img, [cercle_image(h, rayon).astype(np.int32)], True, (0, 200, 255), 1)
    if detection is not None:
        cv2.drawContours(img, [detection.contour], -1, (0, 0, 255), 1)
        x, y = map(int, detection.point)
        cv2.circle(img, (x, y), 6, (0, 255, 0), 2)
    ok, jpeg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise RuntimeError("encodage JPEG impossible")
    return jpeg.tobytes()
