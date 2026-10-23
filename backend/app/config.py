"""Chargement et validation de config/arc-replay.yml."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

ID_CAMERA = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
DEBIT = re.compile(r"^\d+(\.\d+)?[kKmM]?$")


class Camera(BaseModel):
    id: str
    nom: str
    type: Literal["usb", "reseau", "rtsp"]

    # Caméra USB
    peripherique: Optional[str] = None
    format_entree: Literal["mjpeg", "h264", "yuyv422"] = "mjpeg"
    largeur: int = Field(1280, ge=160, le=3840)
    hauteur: int = Field(720, ge=120, le=2160)
    fps: int = Field(30, ge=1, le=240)
    encodeur: Literal["libx264", "copy", "vaapi", "v4l2m2m"] = "libx264"
    debit: str = "4M"

    # Caméra IP
    url: Optional[str] = None

    # Affichage
    miroir_gaucher: bool = False
    ralenti: bool = False

    @field_validator("id")
    @classmethod
    def _id_valide(cls, v: str) -> str:
        if not ID_CAMERA.match(v):
            raise ValueError(
                "identifiant de caméra invalide : minuscules, chiffres, - et _ uniquement"
            )
        return v

    @field_validator("debit")
    @classmethod
    def _debit_valide(cls, v: str) -> str:
        if not DEBIT.match(v):
            raise ValueError("débit invalide (exemples : 4M, 2500k)")
        return v

    @model_validator(mode="after")
    def _coherence(self) -> "Camera":
        if self.type == "usb":
            if not self.peripherique:
                raise ValueError(f"caméra {self.id} : 'peripherique' est requis pour une caméra USB")
            if any(c.isspace() for c in self.peripherique):
                raise ValueError(f"caméra {self.id} : le chemin du périphérique ne doit pas contenir d'espace")
            if self.encodeur == "copy" and self.format_entree != "h264":
                raise ValueError(
                    f"caméra {self.id} : encodeur 'copy' possible uniquement avec format_entree 'h264'"
                )
        if self.type == "rtsp" and not (self.url and self.url.startswith(("rtsp://", "rtsps://"))):
            raise ValueError(f"caméra {self.id} : 'url' rtsp:// requise pour une caméra IP")
        return self


class Serveur(BaseModel):
    delai_s: float = Field(10, ge=1, le=30)
    lateralite: Literal["droitier", "gaucher"] = "droitier"
    usb_chemin: str = "/media/hote/arc-usb"
    usb_verifier_montage: bool = True
    mediamtx_api: str = "http://mediamtx:9997"
    mediamtx_playback: str = "http://mediamtx:9996"
    donnees: str = "/data"


class Volees(BaseModel):
    fleches_par_volee: int = Field(6, ge=1, le=36)
    nouvelle_apres_s: float = Field(90, ge=5)


class Clips(BaseModel):
    avant_s: float = Field(6, ge=0, le=30)
    apres_s: float = Field(3, ge=0, le=30)
    marge_s: float = Field(2, ge=0, le=30)


class Lacher(BaseModel):
    anti_rebond_s: float = Field(2, ge=0)
    decalage_manuel_s: float = Field(1.0, ge=0, le=10)


class Config(BaseModel):
    serveur: Serveur = Serveur()
    volees: Volees = Volees()
    clips: Clips = Clips()
    lacher: Lacher = Lacher()
    cameras: list[Camera] = []

    @model_validator(mode="after")
    def _ids_uniques(self) -> "Config":
        ids = [c.id for c in self.cameras]
        doublons = {i for i in ids if ids.count(i) > 1}
        if doublons:
            raise ValueError(f"identifiants de caméra en double : {', '.join(sorted(doublons))}")
        return self

    def camera(self, cam_id: str) -> Optional[Camera]:
        return next((c for c in self.cameras if c.id == cam_id), None)


def chemin_config() -> Path:
    return Path(os.environ.get("ARC_CONFIG", "/config/arc-replay.yml"))


def charger(chemin: Optional[Path] = None) -> Config:
    chemin = chemin or chemin_config()
    with open(chemin, encoding="utf-8") as f:
        brut = yaml.safe_load(f) or {}
    config = Config.model_validate(brut)
    # Variables d'environnement prioritaires (utile hors Docker)
    if "ARC_DONNEES" in os.environ:
        config.serveur.donnees = os.environ["ARC_DONNEES"]
    if "ARC_MEDIAMTX_API" in os.environ:
        config.serveur.mediamtx_api = os.environ["ARC_MEDIAMTX_API"]
    if "ARC_MEDIAMTX_PLAYBACK" in os.environ:
        config.serveur.mediamtx_playback = os.environ["ARC_MEDIAMTX_PLAYBACK"]
    return config
