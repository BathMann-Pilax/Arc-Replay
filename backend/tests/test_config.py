from pathlib import Path

import pytest
from pydantic import ValidationError

from app import config as cfg
from app.mediamtx import commande_ffmpeg_usb, conf_chemin

RACINE = Path(__file__).resolve().parents[2]


def test_config_exemple_valide():
    c = cfg.charger(RACINE / "config" / "arc-replay.yml")
    # Exemple réglé pour un Pi 3B+ : deux caméras USB en encodeur matériel, pas de ralenti
    assert [cam.id for cam in c.cameras] == ["profil", "arriere", "cible"]
    assert c.camera("profil").encodeur == "v4l2m2m"
    assert not any(cam.ralenti for cam in c.cameras)


def test_ids_en_double_refuses():
    with pytest.raises(ValidationError):
        cfg.Config.model_validate({"cameras": [
            {"id": "a", "nom": "A", "type": "reseau"},
            {"id": "a", "nom": "B", "type": "reseau"},
        ]})


@pytest.mark.parametrize("cam", [
    {"id": "Profil", "nom": "x", "type": "reseau"},                       # majuscule
    {"id": "p", "nom": "x", "type": "usb"},                               # pas de périphérique
    {"id": "p", "nom": "x", "type": "usb", "peripherique": "/dev/video0", "encodeur": "copy"},
    {"id": "p", "nom": "x", "type": "rtsp", "url": "http://cam"},
    {"id": "p", "nom": "x", "type": "usb", "peripherique": "/dev/video0 ; rm -rf /"},
])
def test_cameras_invalides(cam):
    with pytest.raises(ValidationError):
        cfg.Config.model_validate({"cameras": [cam]})


def test_commande_ffmpeg_usb():
    cam = cfg.Camera(id="face", nom="Face", type="usb", peripherique="/dev/video0", fps=100, debit="10M")
    cmd = commande_ffmpeg_usb(cam)
    assert "-input_format mjpeg -framerate 100 -video_size 1280x720 -i /dev/video0" in cmd
    assert "-g 100" in cmd and "-b:v 10M" in cmd
    assert cmd.endswith("rtsp://localhost:$RTSP_PORT/$MTX_PATH")


def test_commande_ffmpeg_copie():
    cam = cfg.Camera(id="p", nom="P", type="usb", peripherique="/dev/video0",
                     format_entree="h264", encodeur="copy")
    assert "-c:v copy" in commande_ffmpeg_usb(cam)
    assert "libx264" not in commande_ffmpeg_usb(cam)


def test_conf_chemins():
    assert conf_chemin(cfg.Camera(id="c", nom="C", type="reseau")) == {"source": "publisher"}
    assert conf_chemin(cfg.Camera(id="c", nom="C", type="rtsp", url="rtsp://10.42.0.5/s")) == {
        "source": "rtsp://10.42.0.5/s"
    }
    usb = conf_chemin(cfg.Camera(id="c", nom="C", type="usb", peripherique="/dev/video0"))
    assert usb["source"] == "publisher" and usb["runOnInitRestart"] is True


def test_camera_cible_directe():
    cam = cfg.Camera.model_validate({"id": "cible", "nom": "Cible", "type": "reseau", "direct": True,
                                     "detection": False, "cadrage": {"zoom_max": 6},
                                     "largeur": 1920, "hauteur": 1080, "debit": "2500k"})
    n = cam.config_noeud()
    assert n == {"capteur": "complet", "largeur": 1920, "hauteur": 1080, "fps": None,
                 "debit": 2_500_000, "cadrage": {"zoom_max": 6, "pas_zoom": 1.25, "pas_deplacement": 0.1}}
    assert cfg.Camera.model_validate({"id": "c", "nom": "C", "type": "reseau", "fps": 15}).config_noeud()["fps"] == 15
    # Ancien nom « recadrage: true » : cadrage par défaut
    assert cfg.Camera.model_validate({"id": "c", "nom": "C", "type": "reseau", "recadrage": True}).cadrage
    with pytest.raises(ValidationError):
        cfg.Camera.model_validate({"id": "u", "nom": "U", "type": "usb", "peripherique": "/dev/x", "cadrage": {}})
    c = cfg.Config.model_validate({"cameras": [cam.model_dump()]})
    assert c.score_actif is False
    assert cfg.Config.model_validate({"cameras": []}).score_actif is True
