"""Blasons et calcul du score (règles World Archery), repris du moteur d'ArcAssist.

Repère des impacts : millimètres, origine au centre de la disposition (spot du
milieu pour un trispot), x vers la droite, y vers le HAUT.
"""

from __future__ import annotations

import math
from typing import Literal, Optional

from pydantic import BaseModel, Field

# En dessous de cette distance à une ligne, un impact détecté par la caméra cible
# est marqué « à confirmer » : la détection n'est pas assez précise pour trancher.
SEUIL_DOUTE_MM = 1.5


class Blason(BaseModel):
    # Diamètre du blason complet de référence : 400 pour un 40 cm comme pour un trispot 40
    diametre_mm: float = Field(1220, gt=0, le=1300)
    # Zone la plus basse imprimée : 1 = blason complet, 5 = 80 cm réduit, 6 = trispot
    zone_min: int = Field(1, ge=1, le=10)
    disposition: Literal["simple", "trispot_vertical", "trispot_triangle"] = "simple"
    ecart_mm: float = Field(220, gt=0, le=1000)  # entre les centres des spots
    # Arc à poulies : 10 réduit (le 10 se limite au cercle intérieur, le reste vaut 9)
    poulies: bool = False


def centres(b: Blason) -> list[tuple[float, float]]:
    """Centre de chaque spot, de haut en bas."""
    s = b.ecart_mm
    if b.disposition == "trispot_vertical":
        return [(0.0, s), (0.0, 0.0), (0.0, -s)]
    if b.disposition == "trispot_triangle":
        h = s * math.sqrt(3) / 2
        return [(0.0, 2 * h / 3), (-s / 2, -h / 3), (s / 2, -h / 3)]
    return [(0.0, 0.0)]


def zones(b: Blason, diametre_mm: Optional[float] = None) -> list[tuple[float, int, bool]]:
    """Zones d'un spot du centre vers l'extérieur : (rayon extérieur en mm, score, est un X)."""
    largeur = (diametre_mm or b.diametre_mm) / 20
    if b.poulies:
        liste = [(largeur / 2, 10, False), (2 * largeur, 9, False)]
    else:
        liste = [(largeur / 2, 10, True), (largeur, 10, False), (2 * largeur, 9, False)]
    liste += [((11 - s) * largeur, s, False) for s in range(8, b.zone_min - 1, -1)]
    return liste


def libelle(score: int, est_x: bool) -> str:
    return "X" if est_x else ("M" if score == 0 else str(score))


def rang(score: int, est_x: bool) -> int:
    """Pour comparer deux flèches : X > 10 > … > M."""
    return 11 if est_x else score


def score_fleche(b: Blason, x_mm: float, y_mm: float, rayon_fleche_mm: float = 2.5,
                 diametre_mm: Optional[float] = None, detecte: bool = True) -> dict:
    """Score d'une flèche seule (sans la règle du trispot).

    Règle de la ligne : on mesure depuis le bord du tube le plus proche du centre,
    une flèche qui touche une ligne compte donc la zone supérieure.
    """
    cs = centres(b)
    spot = min(range(len(cs)), key=lambda i: math.hypot(x_mm - cs[i][0], y_mm - cs[i][1]))
    cx, cy = cs[spot]
    bord = max(0.0, math.hypot(x_mm - cx, y_mm - cy) - rayon_fleche_mm)
    liste = zones(b, diametre_mm)

    score, est_x = 0, False
    for rayon, s, x in liste:
        if bord <= rayon + 1e-9:
            score, est_x = s, x
            break

    # Ligne la plus proche, et valeur de l'autre côté de cette ligne
    ligne_mm, autre = None, None
    for i, (rayon, s, x) in enumerate(liste):
        ecart = abs(bord - rayon)
        if ligne_mm is None or ecart < ligne_mm:
            ligne_mm = ecart
            interieur = libelle(s, x)
            exterieur = libelle(*liste[i + 1][1:]) if i + 1 < len(liste) else "M"
            autre = exterieur if libelle(score, est_x) == interieur else interieur
    doute = bool(detecte and ligne_mm is not None and ligne_mm < SEUIL_DOUTE_MM
                 and autre != libelle(score, est_x))

    hors_spot = score == 0 and len(cs) > 1
    return {
        "score": score,
        "x": est_x,
        "spot": None if hors_spot else spot,
        "rel_x_mm": round(x_mm - cx, 1),  # position dans son spot (groupement d'un trispot)
        "rel_y_mm": round(y_mm - cy, 1),
        "ligne_mm": None if ligne_mm is None else round(ligne_mm, 1),
        "doute": doute,
        "alternative": autre if doute else None,
    }


def appliquer_trispot(b: Blason, impacts: list[dict]) -> None:
    """Trispot : plusieurs flèches dans le même spot, seule la plus faible compte.

    Les autres valent M (`double`). Un score saisi à la main n'est jamais modifié.
    À appeler sur les impacts d'une seule volée.
    """
    for imp in impacts:
        if imp.get("double") and not imp.get("manuel"):
            imp["score"], imp["x"] = imp.get("score_auto", imp["score"]), imp.get("x_auto", imp["x"])
        imp["double"] = False
    if b.disposition == "simple":
        return
    par_spot: dict[int, list[dict]] = {}
    for imp in impacts:
        if imp.get("spot") is not None and imp.get("score"):
            par_spot.setdefault(imp["spot"], []).append(imp)
    for groupe in par_spot.values():
        if len(groupe) < 2:
            continue
        garde = min(groupe, key=lambda i: rang(i["score"], i["x"]))
        for imp in groupe:
            if imp is not garde and not imp.get("manuel"):
                imp["double"], imp["score"], imp["x"] = True, 0, False
