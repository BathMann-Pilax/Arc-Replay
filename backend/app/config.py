"""Chargement et validation de config/arc-replay.yml."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from .blason import Blason

ID_CAMERA = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
DEBIT = re.compile(r"^\d+(\.\d+)?[kKmM]?$")
DELAI_MIN_S = 3
DELAI_MAX_S = 30
DEBIT_UNITES = {"": 1, "k": 1_000, "K": 1_000, "m": 1_000_000, "M": 1_000_000}


class CadrageConfig(BaseModel):
    """Cadrage numérique d'une caméra Raspberry Pi, réglé depuis la télécommande."""
    zoom_max: float = Field(8, ge=1, le=16)
    pas_zoom: float = Field(1.25, gt=1, le=4)          # « zoom + » multiplie le zoom par ce pas
    pas_deplacement: float = Field(0.10, gt=0, le=1)   # part de la largeur visible par flèche


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
    ralenti: bool = False
    # Affichée en direct (WebRTC, < 1 s) au lieu du différé : la vue de la cible
    direct: bool = False

    # Nœud Raspberry Pi (type reseau)
    # Cadrage réglé depuis la télécommande (présence du bloc = cadrage actif)
    cadrage: Optional[CadrageConfig] = None
    recadrage: bool = False  # ancien nom : équivaut à un bloc « cadrage » par défaut
    # Mode du capteur : complet (pleine définition, 10 i/s) ou binne (30 i/s)
    capteur: Literal["complet", "binne"] = "complet"
    # Caméra cible : false = détection d'impact et score désactivés partout
    detection: Optional[bool] = None

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
        if self.recadrage and self.cadrage is None:
            self.cadrage = CadrageConfig()
        if self.cadrage is not None and self.type != "reseau":
            raise ValueError(f"caméra {self.id} : le cadrage ne concerne qu'un nœud Raspberry Pi (type reseau)")
        return self

    def debit_bps(self) -> int:
        """« 4M » -> 4000000, « 2500k » -> 2500000."""
        unite = self.debit[-1] if self.debit[-1] in "kKmM" else ""
        return int(float(self.debit[: len(self.debit) - len(unite)]) * DEBIT_UNITES[unite])

    def config_noeud(self) -> dict:
        """Réglages envoyés au nœud Raspberry Pi à sa connexion (voir noeuds/camera/canal.py)."""
        return {
            "capteur": self.capteur,
            "largeur": self.largeur,
            "hauteur": self.hauteur,
            # Cadence par défaut selon le capteur (10 i/s en pleine définition), sauf si imposée
            "fps": self.fps if "fps" in self.model_fields_set else None,
            "debit": self.debit_bps(),
            "cadrage": self.cadrage.model_dump() if self.cadrage else None,
        }


class Serveur(BaseModel):
    delai_s: float = Field(10, ge=DELAI_MIN_S, le=DELAI_MAX_S)
    lateralite: Literal["droitier", "gaucher"] = "droitier"
    usb_chemin: str = "/media/hote/arc-usb"
    usb_verifier_montage: bool = True
    mediamtx_api: str = "http://mediamtx:9997"
    mediamtx_playback: str = "http://mediamtx:9996"
    donnees: str = "/data"
    # Enregistrements bruts de MediaMTX, purgés au démarrage et en fin de séance
    enregistrements: Optional[str] = "/recordings"
    # Code demandé par la télécommande (vide = pas de code)
    code_telecommande: Optional[str] = Field(None, max_length=64)
    # En dessous, la télécommande affiche une alerte
    alerte_espace_go: float = Field(2, ge=0)
    # Wi-Fi du serveur, pour le QR code de connexion (rempli par point-acces-wifi.sh)
    wifi_ssid: Optional[str] = Field(None, max_length=32)
    wifi_mot_de_passe: Optional[str] = Field(None, max_length=63)
    # Adresse du serveur vue des téléphones (QR code quand l'écran est sur le serveur lui-même)
    adresse_publique: str = "http://10.42.0.1"


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
    blason: Blason = Blason()  # blason par défaut, modifiable depuis la télécommande
    cameras: list[Camera] = []

    @model_validator(mode="after")
    def _ids_uniques(self) -> "Config":
        ids = [c.id for c in self.cameras]
        doublons = {i for i in ids if ids.count(i) > 1}
        if doublons:
            raise ValueError(f"identifiants de caméra en double : {', '.join(sorted(doublons))}")
        return self

    @property
    def score_actif(self) -> bool:
        """Détection d'impact et score : désactivés si une caméra porte « detection: false »."""
        return not any(c.detection is False for c in self.cameras)

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
    if "ARC_ENREGISTREMENTS" in os.environ:
        config.serveur.enregistrements = os.environ["ARC_ENREGISTREMENTS"] or None
    if "ARC_MEDIAMTX_PLAYBACK" in os.environ:
        config.serveur.mediamtx_playback = os.environ["ARC_MEDIAMTX_PLAYBACK"]
    return config
