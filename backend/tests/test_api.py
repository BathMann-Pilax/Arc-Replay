"""Tests de bout en bout du back-end, sans MediaMTX (extraction simulée)."""

import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app import clips, main, mediamtx


@pytest.fixture
def client(tmp_path, monkeypatch):
    usb_dir = tmp_path / "usb"
    usb_dir.mkdir()
    fichier = tmp_path / "arc-replay.yml"
    fichier.write_text(yaml.safe_dump({
        "serveur": {"usb_chemin": str(usb_dir), "usb_verifier_montage": False,
                    "donnees": str(tmp_path / "data")},
        "clips": {"avant_s": 1, "apres_s": 0, "marge_s": 0},
        "lacher": {"anti_rebond_s": 0.5},
        "cameras": [
            {"id": "profil", "nom": "Profil", "type": "reseau"},
            {"id": "cible", "nom": "Cible", "type": "reseau"},
        ],
    }))
    monkeypatch.setenv("ARC_CONFIG", str(fichier))
    monkeypatch.delenv("ARC_DONNEES", raising=False)

    async def faux_extraire(client, playback, camera_id, debut, duree, destination: Path):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"\x00" * 1000)

    async def fausse_synchro(api, cameras, tentatives=60):
        return []

    monkeypatch.setattr(clips, "extraire", faux_extraire)
    monkeypatch.setattr(mediamtx, "synchroniser", fausse_synchro)
    with TestClient(main.app) as c:
        yield c


def attendre(client, condition, delai=5):
    fin = time.time() + delai
    while time.time() < fin:
        etat = client.get("/api/etat").json()
        if condition(etat):
            return etat
        time.sleep(0.05)
    raise AssertionError("condition jamais atteinte")


def test_fleche_clips_rejeu_impact_export(client, tmp_path):
    r = client.post("/api/lacher", json={"source": "audio"}).json()
    assert r["id"] == "V01_F1"
    assert client.post("/api/lacher", json={}).json()["ignore"]  # anti-rebond

    etat = attendre(client, lambda e: e["fleches"][0]["statut"] == "pret")
    f = etat["fleches"][0]
    assert set(f["clips"]) == {"profil", "cible"}
    assert f["clips"]["profil"].endswith("volee01/fleche1/V01_F1_profil.mp4")

    # Rejeu de la dernière flèche, puis ralenti
    assert client.post("/api/commande", json={"action": "rejeu"}).status_code == 200
    client.post("/api/commande", json={"action": "rejeu_controle", "vitesse": 0.25})
    rejeu = client.get("/api/etat").json()["rejeu"]
    assert rejeu["fleche_id"] == "V01_F1" and rejeu["vitesse"] == 0.25

    # Impact au centre d'un blason de 40 cm
    imp = client.post("/api/impact", json={"x_mm": 1, "y_mm": 2, "diametre_mm": 400}).json()
    assert imp["impact"]["score"] == 10 and imp["impact"]["x"]

    # Export vers la « clé »
    client.post("/api/commande", json={"action": "export_usb"})
    etat = attendre(client, lambda e: e["usb"]["export"]["etat"] == "termine")
    seance_id = etat["seance"]["id"]
    dossier = tmp_path / "usb" / "arc-replay" / seance_id / "volee01" / "fleche1"
    assert (dossier / "V01_F1_profil.mp4").exists()
    assert (dossier / "impact.json").exists()
    assert (tmp_path / "usb" / "arc-replay" / seance_id / "seance.csv").exists()


def test_commandes_affichage(client):
    assert client.post("/api/commande", json={"action": "delai", "valeur": 50}).status_code == 200
    assert client.get("/api/etat").json()["delai_s"] == 30  # borné

    client.post("/api/commande", json={"action": "lateralite", "valeur": "gaucher"})
    client.post("/api/commande", json={"action": "disposition", "ordre": ["cible", "profil"],
                                        "masquees": ["profil"]})
    client.post("/api/commande", json={"action": "focus", "camera": "cible"})
    e = client.get("/api/etat").json()
    assert e["lateralite"] == "gaucher"
    assert e["disposition"] == {"ordre": ["cible", "profil"], "masquees": ["profil"], "focus": "cible"}

    r = client.post("/api/commande", json={"action": "disposition", "ordre": ["cible"]})
    assert r.status_code == 400


def test_rejeu_impossible_sans_clip(client):
    assert client.post("/api/commande", json={"action": "rejeu"}).status_code == 404


def test_websocket_diffuse_l_etat(client):
    with client.websocket_connect("/api/ws") as ws:
        premier = ws.receive_json()
        assert premier["type"] == "etat" and premier["etat"]["volee"] == 1
        client.post("/api/commande", json={"action": "marquer"})
        recu = ws.receive_json()
        assert recu["etat"]["fleches"][0]["id"] == "V01_F1"
        ws.send_text("ping")
        while (m := ws.receive_json())["type"] != "pong":
            pass
        assert m["heure_serveur"] > 0
