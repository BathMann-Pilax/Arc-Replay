"""Tests de la détection sur des images de synthèse (pas besoin de Pi)."""

import cv2
import numpy as np
import pytest

import detection

LARGEUR, HAUTEUR = 640, 480
DIAMETRE = 400  # blason de 40 cm
# Blason vu légèrement en biais : ellipse centrée en (320, 240)
POINTS = [(320, 60), (520, 240), (320, 420), (120, 240)]  # haut, droite, bas, gauche


def blason() -> np.ndarray:
    img = np.full((HAUTEUR, LARGEUR), 90, np.uint8)
    for zone in range(10):
        rx, ry = 200 * (10 - zone) / 10, 180 * (10 - zone) / 10
        cv2.ellipse(img, (320, 240), (int(rx), int(ry)), 0, 0, 360, 60 + 18 * zone, -1)
    return img


def avec_fleche(img: np.ndarray, entree: tuple[int, int]) -> np.ndarray:
    """Le tube part du point d'entrée et dépasse vers le bas de l'image."""
    out = img.copy()
    x, y = entree
    cv2.line(out, (x, y), (x + 6, y + 45), 255, 3)
    return out


def test_homographie_bord_et_centre():
    h = detection.homographie(POINTS, DIAMETRE)
    assert detection.vers_mm(h, (320, 240)) == pytest.approx((0, 0), abs=0.5)
    assert detection.vers_mm(h, (520, 240)) == pytest.approx((200, 0), abs=0.5)
    assert detection.vers_mm(h, (320, 60)) == pytest.approx((0, 200), abs=0.5)  # y vers le haut


def test_detection_nouvelle_fleche():
    h = detection.homographie(POINTS, DIAMETRE)
    masque = detection.masque_blason(h, (HAUTEUR, LARGEUR), DIAMETRE)
    avant = avec_fleche(blason(), (250, 200))  # flèche déjà présente
    apres = avec_fleche(avant, (340, 230))     # nouvelle flèche
    d = detection.detecter(avant, apres, masque, extremite="haut")
    assert d is not None
    assert d.point == pytest.approx((340, 230), abs=3)
    x_mm, y_mm = detection.vers_mm(h, d.point)
    assert x_mm == pytest.approx(20, abs=3) and y_mm == pytest.approx(11, abs=3)


def test_rien_hors_du_blason():
    h = detection.homographie(POINTS, DIAMETRE)
    masque = detection.masque_blason(h, (HAUTEUR, LARGEUR), DIAMETRE)
    avant = blason()
    apres = avec_fleche(avant, (20, 20))  # dans la paille, hors blason
    assert detection.detecter(avant, apres, masque) is None


def test_changement_global_de_lumiere_ignore():
    avant = blason()
    apres = cv2.add(avant, np.full_like(avant, 12))
    assert detection.detecter(avant, apres) is None


def test_annotation_jpeg():
    h = detection.homographie(POINTS, DIAMETRE)
    assert detection.annoter(blason(), h, DIAMETRE, None)[:2] == b"\xff\xd8"
