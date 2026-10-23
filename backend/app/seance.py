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


def nouvel_id_seance(heure: Optional[datetime] = None) -> str:
    heure = heure or maintenant()
    return heure.strftime("%Y-%m-%d_%Hh%M")


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
    etat["seance"] = {"id": nouvel_id_seance(heure), "debut": heure.isoformat()}
    etat["volee"] = 1
    etat["fleche"] = 0
    etat["fleches"] = []
    etat["rejeu"] = None


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
