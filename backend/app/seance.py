"""Logique de séance : volées, flèches, impacts.

Fonctions pures sur le dictionnaire d'état, pour pouvoir les tester sans serveur.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath
from typing import Optional

from .config import Config


def maintenant() -> datetime:
    return datetime.now().astimezone()


def nouvel_id_seance(heure: Optional[datetime] = None, precedent: Optional[str] = None) -> str:
    """Nom du dossier de séance, unique même si on en ouvre deux dans la même seconde."""
    heure = heure or maintenant()
    base = heure.strftime("%Y-%m-%d_%Hh%Mm%S")
    if precedent is None or not precedent.startswith(base):
        return base
    suffixe = precedent[len(base):].lstrip("-")
    return f"{base}-{int(suffixe) + 1 if suffixe.isdigit() else 2}"


def etat_initial(config: Config, heure: Optional[datetime] = None) -> dict:
    heure = heure or maintenant()
    return {
        "seance": {"id": nouvel_id_seance(heure), "debut": heure.isoformat()},
        "volee": 1,
        "fleche": 0,  # nombre de flèches tirées dans la volée en cours
        "delai_s": config.serveur.delai_s,
        "lateralite": config.serveur.lateralite,
        "disposition": {
            "ordre": [c.id for c in config.cameras],
            "masquees": [],
            "focus": None,
        },
        "afficher_qr": True,
        "fleches": [],
        "volees_archivees": [],  # volées dont les fichiers ont quitté le serveur
        "rejeu": None,
    }


def reconcilier_disposition(etat: dict, config: Config) -> None:
    """Garde l'ordre choisi, retire les caméras disparues, ajoute les nouvelles."""
    ids = [c.id for c in config.cameras]
    disp = etat.setdefault("disposition", {"ordre": [], "masquees": [], "focus": None})
    ordre = [i for i in disp.get("ordre", []) if i in ids]
    ordre += [i for i in ids if i not in ordre]
    disp["ordre"] = ordre
    disp["masquees"] = [i for i in disp.get("masquees", []) if i in ids]
    if disp.get("focus") not in ids:
        disp["focus"] = None


def id_fleche(volee: int, numero: int) -> str:
    return f"V{volee:02d}_F{numero}"


def dossier_fleche(seance_id: str, volee: int, numero: int) -> PurePosixPath:
    """Chemin relatif au dossier des séances : <seance>/volee01/fleche2"""
    return PurePosixPath(seance_id) / f"volee{volee:02d}" / f"fleche{numero}"


def nom_clip(fleche_id: str, camera_id: str) -> str:
    return f"{fleche_id}_{camera_id}.mp4"


def enregistrer_lacher(etat: dict, config: Config, heure: datetime) -> Optional[dict]:
    """Ajoute une flèche à la séance. Renvoie la flèche, ou None si anti-rebond.

    Une nouvelle volée commence automatiquement quand la volée est pleine
    ou après une longue pause sans tir (le temps d'aller aux cibles).
    """
    fleches = etat["fleches"]
    if fleches:
        precedente = datetime.fromisoformat(fleches[-1]["heure"])
        ecart = (heure - precedente).total_seconds()
        if 0 <= ecart < config.lacher.anti_rebond_s:
            return None
        if etat["fleche"] > 0 and (
            etat["fleche"] >= config.volees.fleches_par_volee
            or ecart > config.volees.nouvelle_apres_s
        ):
            etat["volee"] += 1
            etat["fleche"] = 0

    etat["fleche"] += 1
    volee, numero = etat["volee"], etat["fleche"]
    fid = id_fleche(volee, numero)
    dossier = dossier_fleche(etat["seance"]["id"], volee, numero)
    fleche = {
        "id": fid,
        "volee": volee,
        "numero": numero,
        "heure": heure.isoformat(),
        "statut": "en_cours",  # en_cours -> pret | partiel | erreur
        "dossier": str(dossier),
        "clips": {},  # id caméra -> chemin relatif du fichier
        "impact": None,
        "archivee": False,  # vrai quand les clips ont quitté le serveur (clé USB ou purge)
    }
    fleches.append(fleche)
    return fleche


def nouvelle_volee(etat: dict) -> bool:
    """Passe à la volée suivante, sauf si la volée en cours est vide."""
    if etat["fleche"] == 0:
        return False
    etat["volee"] += 1
    etat["fleche"] = 0
    return True


def nouvelle_seance(etat: dict, heure: Optional[datetime] = None) -> None:
    heure = heure or maintenant()
    precedent = (etat.get("seance") or {}).get("id")
    etat["seance"] = {"id": nouvel_id_seance(heure, precedent), "debut": heure.isoformat()}
    etat["volee"] = 1
    etat["fleche"] = 0
    etat["fleches"] = []
    etat["volees_archivees"] = []
    etat["rejeu"] = None


def annuler_derniere(etat: dict) -> Optional[dict]:
    """Retire la dernière flèche (faux lâcher), si elle appartient à la volée en cours.

    Renvoie la flèche retirée, ou None s'il n'y a rien à annuler.
    """
    if not etat["fleches"] or etat["fleche"] == 0:
        return None
    f = etat["fleches"][-1]
    if f["volee"] != etat["volee"] or f.get("archivee"):
        return None
    etat["fleches"].pop()
    etat["fleche"] = f["numero"] - 1
    rejeu = etat.get("rejeu")
    if rejeu and f["id"] in (rejeu.get("fleche_id"), rejeu.get("fleche_id_b")):
        etat["rejeu"] = None
    return f


def volees_a_archiver(etat: dict, toutes: bool = False) -> list[int]:
    """Volées terminées dont les fichiers sont encore sur le serveur.

    Une volée attend que tous ses clips soient découpés. `toutes` inclut la
    volée en cours (fin de séance).
    """
    deja = set(etat.get("volees_archivees", []))
    resultat = []
    for v in sorted({f["volee"] for f in etat["fleches"]}):
        if v in deja or (v >= etat["volee"] and not toutes):
            continue
        if any(f["statut"] == "en_cours" for f in etat["fleches"] if f["volee"] == v):
            continue
        resultat.append(v)
    return resultat


def marquer_archivee(etat: dict, volee: int) -> None:
    """Les fichiers de la volée ne sont plus sur le serveur : on garde scores et positions."""
    if volee not in etat.setdefault("volees_archivees", []):
        etat["volees_archivees"].append(volee)
    for f in etat["fleches"]:
        if f["volee"] == volee:
            f["archivee"] = True
            f["clips"] = {}
            if f.get("impact"):
                f["impact"]["image"] = None
    rejeu = etat.get("rejeu")
    if rejeu:
        ids = {f["id"] for f in etat["fleches"] if f["volee"] == volee}
        if ids & {rejeu.get("fleche_id"), rejeu.get("fleche_id_b")}:
            etat["rejeu"] = None


def dossier_volee(seance_id: str, volee: int) -> PurePosixPath:
    return PurePosixPath(seance_id) / f"volee{volee:02d}"


def impact_manuel(f: dict, score: int, est_x: bool) -> dict:
    """Score saisi à la main : garde la position mesurée s'il y en a une."""
    impact = dict(f.get("impact") or {
        "x_mm": None, "y_mm": None, "diametre_mm": None, "image": None,
    })
    impact["score"] = score
    impact["x"] = bool(est_x) and score == 10
    impact["manuel"] = True
    return impact


def groupement(impacts: list[dict]) -> Optional[dict]:
    """Centre et dispersion d'un ensemble d'impacts positionnés (au moins 2).

    La dispersion est la distance moyenne des impacts au centre, en mm.
    """
    points = [(i["x_mm"], i["y_mm"]) for i in impacts
              if i and i.get("x_mm") is not None and i.get("y_mm") is not None]
    if len(points) < 2:
        return None
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    dispersion = sum(((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 for x, y in points) / len(points)
    return {"n": len(points), "centre_x_mm": round(cx, 1), "centre_y_mm": round(cy, 1),
            "dispersion_mm": round(dispersion, 1)}


def groupements(etat: dict) -> dict:
    """Groupement de la volée en cours, de la séance, et de chaque volée."""
    par_volee = {}
    for v in sorted({f["volee"] for f in etat["fleches"]}):
        g = groupement([f["impact"] for f in etat["fleches"] if f["volee"] == v])
        if g:
            par_volee[v] = g
    return {
        "volee": par_volee.get(etat["volee"]),
        "seance": groupement([f["impact"] for f in etat["fleches"]]),
        "par_volee": par_volee,
    }


def trouver_fleche(etat: dict, fleche_id: Optional[str]) -> Optional[dict]:
    """Par identifiant ; 'derniere' ou None donne la dernière flèche."""
    if not etat["fleches"]:
        return None
    if fleche_id in (None, "derniere"):
        return etat["fleches"][-1]
    return next((f for f in etat["fleches"] if f["id"] == fleche_id), None)


def fleche_pour_impact(etat: dict, fleche_id: Optional[str]) -> Optional[dict]:
    """Flèche visée par un impact : celle indiquée, sinon la plus récente sans impact."""
    if fleche_id:
        return trouver_fleche(etat, fleche_id)
    for f in reversed(etat["fleches"]):
        if f["impact"] is None:
            return f
    return None


def score_wa(distance_mm: float, diametre_mm: float, rayon_fleche_mm: float = 2.5) -> tuple[int, bool]:
    """Score d'un impact sur un blason World Archery à 10 zones.

    Une flèche qui touche une ligne compte la zone supérieure : on retire le
    rayon du tube à la distance au centre. Renvoie (score, est_un_X).
    """
    largeur_zone = diametre_mm / 20
    d = max(0.0, distance_mm - rayon_fleche_mm)
    zone = int(d // largeur_zone)
    score = max(0, 10 - zone)
    est_x = d <= largeur_zone / 2
    return score, est_x


CSV_ENTETE = "volee;fleche;heure;score;x;x_mm;y_mm;statut;fichiers\n"
CSV_GROUPEMENTS_ENTETE = "volee;impacts;centre_x_mm;centre_y_mm;dispersion_mm\n"


def ligne_csv(f: dict) -> str:
    imp = f.get("impact") or {}
    score = imp.get("score")
    return ";".join(
        [
            str(f["volee"]),
            str(f["numero"]),
            datetime.fromisoformat(f["heure"]).astimezone().strftime("%H:%M:%S"),
            "" if score is None else str(score),
            "X" if imp.get("x") else "",
            "" if imp.get("x_mm") is None else f"{imp['x_mm']:.1f}",
            "" if imp.get("y_mm") is None else f"{imp['y_mm']:.1f}",
            f["statut"],
            f["dossier"],
        ]
    ) + "\n"


def contenu_csv(etat: dict) -> str:
    return CSV_ENTETE + "".join(ligne_csv(f) for f in etat["fleches"])


def contenu_csv_groupements(etat: dict) -> str:
    g = groupements(etat)
    lignes = [(str(v), d) for v, d in g["par_volee"].items()]
    if g["seance"]:
        lignes.append(("seance", g["seance"]))
    return CSV_GROUPEMENTS_ENTETE + "".join(
        f"{nom};{d['n']};{d['centre_x_mm']:.1f};{d['centre_y_mm']:.1f};{d['dispersion_mm']:.1f}\n"
        for nom, d in lignes
    )
