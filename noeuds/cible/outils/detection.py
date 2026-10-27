"""Détection de l'impact d'une flèche sur le blason (extrait d'Arc Replay).

Principe :
1. on compare une image prise avant la flèche et une image prise après :
   seule la nouvelle flèche a changé ;
2. on garde la plus grande zone de changement à l'intérieur du blason ;
3. on en tire un point (extrémité d'un côté donné, ou centre pour une vue de face) ;
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
    point: Point          # point d'impact estimé, en pixels
    aire: float           # surface de la zone de changement, en pixels
    contour: np.ndarray
    fiable: bool = True   # False : tube peu visible, position approximative


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


# --- Vue de face (caméra au pas de tir) -------------------------------------

def px_par_mm(h: np.ndarray, diametre_mm: float) -> float:
    """Échelle moyenne de l'image sur le blason, en pixels par millimètre."""
    centre = vers_image(h, np.float32([[0, 0]]))[0]
    bord = cercle_image(h, diametre_mm / 2, n=36)
    return float(np.mean(np.linalg.norm(bord - centre, axis=1)) / (diametre_mm / 2))


def aligner(reference: np.ndarray, image: np.ndarray, masque: Optional[np.ndarray] = None,
            reduction: int = 4) -> tuple[np.ndarray, float]:
    """Recale `image` sur `reference` si le blason a un peu bougé (papier qui
    balance, butte poussée par la flèche). Renvoie l'image recalée et le
    déplacement estimé en pixels (0 si le recalage a échoué)."""
    def petit(img):
        return cv2.resize(img, None, fx=1 / reduction, fy=1 / reduction,
                          interpolation=cv2.INTER_AREA).astype(np.float32)

    ref, img = petit(reference), petit(image)
    m = None
    if masque is not None:
        m = cv2.resize(masque, (ref.shape[1], ref.shape[0]), interpolation=cv2.INTER_NEAREST)
    warp = np.eye(2, 3, dtype=np.float32)
    critere = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-5)
    try:
        _, warp = cv2.findTransformECC(ref, img, warp, cv2.MOTION_AFFINE, critere, m, 5)
    except cv2.error:
        return image, 0.0
    warp[:, 2] *= reduction
    recale = cv2.warpAffine(image, warp, (image.shape[1], image.shape[0]),
                            flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
                            borderMode=cv2.BORDER_REPLICATE)
    # Déplacement mesuré au centre de l'image (inclut une éventuelle rotation)
    centre = np.array([image.shape[1] / 2, image.shape[0] / 2, 1.0])
    deplacement = warp @ centre - centre[:2]
    return recale, float(np.hypot(*deplacement))


def point_entree(zone: np.ndarray) -> tuple[float, float, bool]:
    """Point d'entrée d'une flèche vue de face : le bout fin (pointe du tube),
    à l'opposé de l'empennage. `zone` : masque des pixels de la flèche.

    Renvoie (x, y, fiable). « Pas fiable » quand on ne distingue pas le tube :
    flèche vue de bout, ou tube foncé sur une zone foncée (seul l'empennage
    ressort alors, et son centre n'est pas le point d'entrée)."""
    ys, xs = np.nonzero(zone)
    p = np.stack([xs, ys], axis=1).astype(np.float64)
    moy = p.mean(axis=0)
    q = p - moy
    valeurs, vecteurs = np.linalg.eigh(np.cov(q.T))
    if valeurs[0] <= 0 or valeurs[1] / valeurs[0] < 2:  # tache presque ronde : flèche vue de bout
        return float(moy[0]), float(moy[1]), False
    t = q @ vecteurs[:, 1]   # le long de la flèche
    s = q @ vecteurs[:, 0]   # en travers
    tmin, tmax = t.min(), t.max()
    longueur = tmax - tmin

    def largeur(sel):
        return np.percentile(s[sel], 95) - np.percentile(s[sel], 5)

    l_min = largeur(t < tmin + 0.25 * longueur)
    l_max = largeur(t > tmax - 0.25 * longueur)
    cote_min_fin = l_min <= l_max
    sel = t < tmin + 0.03 * longueur if cote_min_fin else t > tmax - 0.03 * longueur
    x, y = p[sel].mean(axis=0)
    # Les deux bouts ont presque la même largeur : on ne sait pas lequel est la pointe
    fiable = min(l_min, l_max) < 0.6 * max(l_min, l_max)
    return float(x), float(y), bool(fiable)


def carte_changements(avant: np.ndarray, apres: np.ndarray, px_mm: float,
                      fond_mm: float = 8) -> np.ndarray:
    """Changements nets entre deux images, en contraste relatif (0,3 = 30 %).

    On compare les logarithmes (un changement d'éclairage devient un simple
    décalage) puis on retire les variations douces, plus larges que
    ~`fond_mm` : ombre qui glisse, papier qui gondole différemment, nuage.
    Une flèche, aux bords nets, reste."""
    la = np.log1p(cv2.GaussianBlur(avant, (5, 5), 0).astype(np.float32))
    lb = np.log1p(cv2.GaussianBlur(apres, (5, 5), 0).astype(np.float32))
    d = lb - la
    return np.abs(d - cv2.GaussianBlur(d, (0, 0), fond_mm * px_mm))


def detecter_face(
    avant: np.ndarray,
    apres: np.ndarray,
    masque: Optional[np.ndarray],
    px_mm: float,
    seuil: float = 0.30,
    aire_min_mm2: float = 20,
    point: str = "auto",
) -> Optional[Detection]:
    """Comme `detecter`, pour une caméra face au blason.

    - changements mesurés en contraste relatif, sans les variations douces
      (ombres, ondulations du papier) ;
    - liserés de moins de ~2 mm supprimés (bords d'anneaux après un léger
      mouvement) ;
    - morceaux proches regroupés (tube coupé en plusieurs bouts quand il passe
      sur une zone de même teinte), et on garde le groupe qui a le plus changé.
    """
    carte = carte_changements(avant, apres, px_mm)
    binaire = (carte > seuil).astype(np.uint8) * 255
    if masque is not None:
        binaire = cv2.bitwise_and(binaire, masque)
    k = max(3, int(round(2 * px_mm)) | 1)
    binaire = cv2.morphologyEx(binaire, cv2.MORPH_OPEN,
                               cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    if not binaire.any():
        return None

    r = max(3, int(round(12 * px_mm)) | 1)  # morceaux à moins de ~6 mm l'un de l'autre
    groupes = cv2.dilate(binaire, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (r, r)))
    n, etiquettes = cv2.connectedComponents(groupes)
    meilleur, score_max = None, 0.0
    for i in range(1, n):
        zone = (etiquettes == i) & (binaire > 0)
        score = float(carte[zone].sum())
        if score > score_max:
            meilleur, score_max = zone, score
    aire_min = max(20.0, aire_min_mm2 * px_mm ** 2)
    if meilleur is None or meilleur.sum() < aire_min:
        return None

    ys, xs = np.nonzero(meilleur)
    c = cv2.convexHull(np.stack([xs, ys], axis=1).astype(np.int32))  # contour de toute la flèche

    fiable = True
    if point == "auto":
        *xy, fiable = point_entree(meilleur)
    elif point == "centre":
        ys, xs = np.nonzero(meilleur)
        xy = (xs.mean(), ys.mean())
    else:
        pts = c.reshape(-1, 2)
        i = {"haut": pts[:, 1].argmin(), "bas": pts[:, 1].argmax(),
             "gauche": pts[:, 0].argmin(), "droite": pts[:, 0].argmax()}[point]
        xy = (float(pts[i][0]), float(pts[i][1]))
    return Detection(point=(float(xy[0]), float(xy[1])), aire=float(meilleur.sum()),
                     contour=c, fiable=fiable)


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
