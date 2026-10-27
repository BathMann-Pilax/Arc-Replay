"""Tests de bout en bout du back-end, sans MediaMTX (extraction simulée)."""

import os
import threading
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
                    "donnees": str(tmp_path / "data"),
                    "wifi_ssid": "ArcReplay", "wifi_mot_de_passe": "arc;2026"},
        "clips": {"avant_s": 1, "apres_s": 0, "marge_s": 0},
        "lacher": {"anti_rebond_s": 0.5},
        "cameras": [
            {"id": "profil", "nom": "Profil", "type": "reseau"},
            {"id": "cible", "nom": "Cible", "type": "reseau", "direct": True, "cadrage": {}},
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


def test_fleche_clips_rejeu_impact(client):
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


def e_sans_erreur(etat):
    return etat["usb"]["sauvegarde"]["etat"] != "erreur"


def tirer_volee(client, n=2):
    """Tire n flèches dans la volée en cours et attend leurs clips."""
    depart = len(client.get("/api/etat").json()["fleches"])
    for i in range(n):
        if i:
            time.sleep(0.6)  # anti-rebond de 0,5 s
        client.post("/api/lacher", json={})
    return attendre(client, lambda e: len(e["fleches"]) == depart + n
                    and all(f["statut"] == "pret" for f in e["fleches"][depart:]))


def test_sans_cle_seule_la_volee_en_cours_reste(client, tmp_path):
    (tmp_path / "usb").rmdir()  # pas de clé
    attendre(client, lambda e: not e["usb"]["presente"])
    etat = tirer_volee(client)
    seances = tmp_path / "data" / "seances" / etat["seance"]["id"]
    assert (seances / "volee01" / "fleche1" / "V01_F1_profil.mp4").exists()

    client.post("/api/commande", json={"action": "nouvelle_volee"})
    etat = attendre(client, lambda e: 1 in e["volees_archivees"] and not (seances / "volee01").exists())
    assert e_sans_erreur(etat)
    f = etat["fleches"][0]
    assert f["archivee"] and f["clips"] == {}
    # Plus de rejeu possible pour une volée partie
    assert client.post("/api/commande", json={"action": "rejeu", "fleche_id": "V01_F1"}).status_code == 409


def test_avec_cle_chaque_volee_part_sur_la_cle(client, tmp_path):
    attendre(client, lambda e: e["usb"]["presente"])
    etat = tirer_volee(client)
    seance_id = etat["seance"]["id"]
    client.post("/api/commande", json={"action": "nouvelle_volee"})
    attendre(client, lambda e: e["usb"]["sauvegarde"]["etat"] == "ok")
    cle = tmp_path / "usb" / "arc-replay" / seance_id
    assert (cle / "volee01" / "fleche1" / "V01_F1_profil.mp4").exists()
    assert (cle / "volee01" / "fleche2" / "impact.json").exists()
    assert (cle / "seance.csv").exists() and (cle / "groupements.csv").exists()
    assert not (tmp_path / "data" / "seances" / seance_id / "volee01").exists()


def test_sauvegarder_maintenant_garde_la_volee_en_cours(client, tmp_path):
    attendre(client, lambda e: e["usb"]["presente"])
    etat = tirer_volee(client, 1)
    seance_id = etat["seance"]["id"]
    client.post("/api/commande", json={"action": "sauvegarder_usb"})
    attendre(client, lambda e: e["usb"]["sauvegarde"]["etat"] == "ok")
    assert (tmp_path / "usb" / "arc-replay" / seance_id / "volee01" / "fleche1" / "V01_F1_cible.mp4").exists()
    # Toujours sur le serveur : on peut encore la rejouer
    assert client.post("/api/commande", json={"action": "rejeu"}).status_code == 200


def test_fin_de_seance_range_et_vide_le_serveur(client, tmp_path):
    attendre(client, lambda e: e["usb"]["presente"])
    etat = tirer_volee(client, 1)
    ancienne = etat["seance"]["id"]
    assert client.post("/api/commande", json={"action": "nouvelle_seance"}).status_code == 200
    etat = client.get("/api/etat").json()
    assert etat["seance"]["id"] != ancienne and etat["fleches"] == []
    assert (tmp_path / "usb" / "arc-replay" / ancienne / "volee01" / "fleche1" / "V01_F1_profil.mp4").exists()
    assert not (tmp_path / "data" / "seances" / ancienne).exists()


def test_annuler_la_derniere_fleche(client, tmp_path):
    etat = tirer_volee(client, 2)
    dossier = tmp_path / "data" / "seances" / etat["fleches"][1]["dossier"]
    assert dossier.exists()
    assert client.post("/api/commande", json={"action": "annuler_fleche"}).status_code == 200
    etat = client.get("/api/etat").json()
    assert [f["id"] for f in etat["fleches"]] == ["V01_F1"] and etat["fleche"] == 1
    assert not dossier.exists()
    # La flèche suivante reprend le numéro libéré
    assert client.post("/api/lacher", json={}).json()["id"] == "V01_F2"


def test_annulation_pendant_la_decoupe(client, monkeypatch):
    """L'ancienne découpe d'une flèche annulée ne doit pas toucher la flèche qui reprend son numéro."""
    import asyncio
    lent = asyncio.Event()

    async def extraire_lent(client_http, playback, camera_id, debut, duree, destination):
        await lent.wait()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"ancien")

    monkeypatch.setattr(clips, "extraire", extraire_lent)
    client.post("/api/lacher", json={})
    assert client.post("/api/commande", json={"action": "annuler_fleche"}).status_code == 200
    time.sleep(0.6)

    async def extraire_neuf(client_http, playback, camera_id, debut, duree, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"neuf")

    monkeypatch.setattr(clips, "extraire", extraire_neuf)
    nouvelle = client.post("/api/lacher", json={}).json()
    etat = attendre(client, lambda e: e["fleches"] and e["fleches"][0]["statut"] == "pret")
    assert etat["fleches"][0]["heure"] == nouvelle["heure"]
    client.portal.call(lent.set)  # l'ancienne découpe se termine maintenant
    time.sleep(0.3)
    etat = client.get("/api/etat").json()
    assert etat["fleches"][0]["statut"] == "pret" and len(etat["fleches"]) == 1
    clip = main.serveur.seances / etat["fleches"][0]["clips"]["profil"]
    assert clip.read_bytes() == b"neuf"
    assert not list(clip.parent.glob("*.part"))


def test_score_manuel(client):
    client.post("/api/commande", json={"action": "marquer"})
    r = client.post("/api/commande", json={"action": "score", "valeur": 10, "x": True})
    assert r.status_code == 200
    imp = client.get("/api/etat").json()["fleches"][0]["impact"]
    assert imp["score"] == 10 and imp["x"] and imp["manuel"] and imp["x_mm"] is None
    assert client.post("/api/commande", json={"action": "score", "valeur": 11}).status_code == 400


def test_comparaison_de_deux_fleches(client):
    tirer_volee(client, 2)
    r = client.post("/api/commande", json={"action": "comparer", "fleche_id": "V01_F1",
                                            "fleche_id_b": "V01_F2", "camera": "cible"})
    assert r.status_code == 200
    rejeu = client.get("/api/etat").json()["rejeu"]
    assert rejeu["fleche_id_b"] == "V01_F2" and rejeu["camera"] == "cible" and not rejeu["superposer"]
    client.post("/api/commande", json={"action": "rejeu_controle", "superposer": True, "camera": "profil"})
    rejeu = client.get("/api/etat").json()["rejeu"]
    assert rejeu["superposer"] and rejeu["camera"] == "profil"
    r = client.post("/api/commande", json={"action": "comparer", "fleche_id": "V01_F1",
                                            "fleche_id_b": "V01_F1"})
    assert r.status_code == 404


def test_groupements(client):
    tirer_volee(client, 2)
    client.post("/api/impact", json={"fleche_id": "V01_F1", "x_mm": 10, "y_mm": 0, "diametre_mm": 400})
    client.post("/api/impact", json={"fleche_id": "V01_F2", "x_mm": 30, "y_mm": 0, "diametre_mm": 400})
    g = client.get("/api/etat").json()["groupements"]
    assert g["volee"] == {"n": 2, "centre_x_mm": 20.0, "centre_y_mm": 0.0, "dispersion_mm": 10.0}
    assert g["seance"] == g["volee"]


def test_code_telecommande(client):
    main.serveur.config.serveur.code_telecommande = "1234"
    assert client.post("/api/commande", json={"action": "qr", "valeur": False}).status_code == 403
    r = client.post("/api/commande", json={"action": "qr", "valeur": False}, headers={"X-Arc-Code": "1234"})
    assert r.status_code == 200
    assert client.get("/api/etat").json()["code_requis"]
    # Les capteurs (micro, nœud cible) n'ont pas besoin du code
    assert client.post("/api/lacher", json={}).status_code == 200


def test_redemarrage_vide_le_serveur(tmp_path, monkeypatch):
    fichier = tmp_path / "arc-replay.yml"
    enregistrements = tmp_path / "rec" / "profil"
    enregistrements.mkdir(parents=True)
    vieux = enregistrements / "vieux.mp4"
    vieux.write_bytes(b"0")
    os.utime(vieux, (time.time() - 3600, time.time() - 3600))
    recent = enregistrements / "recent.mp4"
    recent.write_bytes(b"0")
    fichier.write_text(yaml.safe_dump({
        "serveur": {"donnees": str(tmp_path / "data"), "enregistrements": str(tmp_path / "rec")},
        "cameras": [],
    }))
    ancienne = tmp_path / "data" / "seances" / "2026-01-01_10h00m00" / "volee01"
    ancienne.mkdir(parents=True)
    (tmp_path / "data" / "etat.json").write_text('{"delai_s": 12, "fleches": [{"id": "x"}]}')
    s = main.Serveur(main.cfg.charger(fichier))
    assert not ancienne.exists()
    assert s.etat["delai_s"] == 12 and s.etat["fleches"] == []
    assert not vieux.exists() and recent.exists()


def test_commandes_affichage(client):
    assert client.post("/api/commande", json={"action": "delai", "valeur": 50}).status_code == 200
    assert client.get("/api/etat").json()["delai_s"] == 30  # borné

    assert client.post("/api/commande", json={"action": "delai", "valeur": 1}).status_code == 200
    assert client.get("/api/etat").json()["delai_s"] == 3  # minimum
    client.post("/api/commande", json={"action": "lateralite", "valeur": "gaucher"})
    client.post("/api/commande", json={"action": "disposition", "ordre": ["cible", "profil"],
                                        "masquees": ["profil"]})
    client.post("/api/commande", json={"action": "focus", "camera": "cible"})
    e = client.get("/api/etat").json()
    assert e["lateralite"] == "gaucher"
    assert e["disposition"] == {"ordre": ["cible", "profil"], "masquees": ["profil"],
                                "miroir": [], "focus": "cible"}

    # Miroir : seules les caméras connues sont gardées, l'ordre et le masquage ne bougent pas
    client.post("/api/commande", json={"action": "disposition", "miroir": ["cible", "inconnue"]})
    d = client.get("/api/etat").json()["disposition"]
    assert d["miroir"] == ["cible"]
    assert d["masquees"] == ["profil"]

    r = client.post("/api/commande", json={"action": "disposition", "ordre": ["cible"]})
    assert r.status_code == 400


def test_rejeu_impossible_sans_clip(client):
    assert client.post("/api/commande", json={"action": "rejeu"}).status_code == 404


def test_websocket_diffuse_l_etat(client):
    with client.websocket_connect("/api/ws") as ws:
        premier = ws.receive_json()
        assert premier["type"] == "etat" and premier["etat"]["volee"] == 1
        client.post("/api/commande", json={"action": "marquer"})
        # La surveillance de la clé et du disque diffuse aussi l'état : on attend la flèche
        while not (recu := ws.receive_json())["etat"]["fleches"]:
            pass
        assert recu["etat"]["fleches"][0]["id"] == "V01_F1"
        ws.send_text("ping")
        while (m := ws.receive_json())["type"] != "pong":
            pass
        assert m["heure_serveur"] > 0


def test_blason_trispot_et_recalcul(client):
    trispot = {"diametre_mm": 400, "zone_min": 6, "disposition": "trispot_vertical", "ecart_mm": 220}
    assert client.post("/api/commande", json={"action": "blason", "blason": trispot}).status_code == 200
    tirer_volee(client, 3)
    # Deux flèches dans le spot du haut, une au centre
    for fid, x, y in [("V01_F1", 0, 222), ("V01_F2", 25, 220), ("V01_F3", 0, 0)]:
        client.post("/api/impact", json={"fleche_id": fid, "x_mm": x, "y_mm": y})
    e = client.get("/api/etat").json()
    assert [(f["impact"]["score"], f["impact"]["double"]) for f in e["fleches"]] == [
        (0, True), (9, False), (10, False)]
    assert [f["impact"]["spot"] for f in e["fleches"]] == [0, 0, 1]
    # Groupement : chaque impact ramené au centre de son spot
    assert e["groupements"]["volee"]["centre_y_mm"] == 0.7

    # Retour au blason simple de 40 cm : la séance est recalculée, plus de doublon
    client.post("/api/commande", json={"action": "blason", "blason": {"diametre_mm": 400}})
    e = client.get("/api/etat").json()
    assert [f["impact"]["score"] for f in e["fleches"]] == [0, 0, 10]  # 220 mm : hors du 40 cm
    assert not any(f["impact"]["double"] for f in e["fleches"])
    assert client.post("/api/commande", json={"action": "blason", "blason": {"zone_min": 12}}).status_code == 422


def test_impact_a_confirmer_puis_tranche(client):
    tirer_volee(client, 1)
    client.post("/api/commande", json={"action": "blason", "blason": {"diametre_mm": 400}})
    f = client.post("/api/impact", json={"x_mm": 21.5, "y_mm": 0}).json()
    assert (f["impact"]["score"], f["impact"]["doute"], f["impact"]["alternative"]) == (10, True, "9")
    client.post("/api/commande", json={"action": "score", "valeur": 9})
    imp = client.get("/api/etat").json()["fleches"][0]["impact"]
    assert (imp["score"], imp["doute"], imp["manuel"]) == (9, False, True)


def test_grille_et_reperes(client):
    def reperes():
        return client.get("/api/etat").json()["reperes"]

    assert client.post("/api/commande", json={"action": "grille", "valeur": True}).status_code == 200
    assert client.get("/api/etat").json()["grille"] is True
    ajout = {"action": "repere_ajouter", "camera": "profil", "points": [0.5, 0.1, 0.5, 0.9]}
    assert client.post("/api/commande", json=ajout).status_code == 200
    client.post("/api/commande", json={**ajout, "points": [0.1, 0.4, 0.9, 0.42]})
    assert reperes() == {"profil": [[0.5, 0.1, 0.5, 0.9], [0.1, 0.4, 0.9, 0.42]]}
    # Refus : caméra inconnue, point hors de l'image, nombre de points
    assert client.post("/api/commande", json={**ajout, "camera": "x"}).status_code == 400
    assert client.post("/api/commande", json={**ajout, "points": [0, 0, 1, 1.2]}).status_code == 400
    assert client.post("/api/commande", json={**ajout, "points": [0, 0, 1]}).status_code == 422
    client.post("/api/commande", json={"action": "repere_supprimer", "camera": "profil", "index": 0})
    assert reperes() == {"profil": [[0.1, 0.4, 0.9, 0.42]]}
    client.post("/api/commande", json={"action": "repere_supprimer", "camera": "profil"})
    assert reperes() == {"profil": []}
    for _ in range(main.REPERES_MAX):
        client.post("/api/commande", json=ajout)
    assert client.post("/api/commande", json=ajout).status_code == 409


def test_reglages_conserves_au_redemarrage(client, tmp_path):
    client.post("/api/commande", json={"action": "grille", "valeur": True})
    client.post("/api/commande", json={"action": "repere_ajouter", "camera": "cible", "points": [0, 0, 1, 1]})
    client.post("/api/commande", json={"action": "blason", "blason": {"diametre_mm": 600}})
    etat = main.srv()._charger_etat()
    assert etat["grille"] is True and etat["reperes"] == {"cible": [[0, 0, 1, 1]]}
    assert etat["blason"]["diametre_mm"] == 600


def test_apercu_camera(client, monkeypatch):
    from app import apercu

    assert client.get("/api/apercu/inconnue").status_code == 404
    vus = []

    def fausse_capture(url):
        vus.append(url)
        return b"\xff\xd8jpeg"

    monkeypatch.setattr(apercu, "capturer", fausse_capture)
    r = client.get("/api/apercu/profil")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content == b"\xff\xd8jpeg"
    assert vus == ["rtsp://mediamtx:8554/profil"]

    def en_panne(url):
        raise RuntimeError("hors ligne")

    monkeypatch.setattr(apercu, "capturer", en_panne)
    assert client.get("/api/apercu/profil").status_code == 503


def test_cadrage_relaye_au_noeud(client):
    # Pas de nœud connecté : la télécommande reçoit une erreur claire
    assert client.post("/api/cadrage/cible", json={"action": "zoomer", "pas": 1}).status_code == 503
    assert client.post("/api/cadrage/profil", json={"action": "reinitialiser"}).status_code == 404

    with client.websocket_connect("/api/noeud/ws?camera=cible") as noeud:
        conf = noeud.receive_json()
        assert conf["type"] == "config"
        assert conf["camera"]["capteur"] == "complet" and conf["camera"]["fps"] is None
        assert conf["camera"]["cadrage"] == {"zoom_max": 8, "pas_zoom": 1.25, "pas_deplacement": 0.1}
        noeud.send_json({"type": "cadrage", "cadrage": {"zoom": 1.0}})
        e = attendre(client, lambda e: e["cadrages"]["cible"].get("zoom") == 1.0)
        assert e["cadrages"]["cible"]["connecte"]

        def commander(corps, resultat):
            resultat["r"] = client.post("/api/cadrage/cible", json=corps)

        # Zoom + : la commande arrive au nœud, son cadrage effectif revient à tous
        resultat = {}
        fil = threading.Thread(target=commander, args=({"action": "zoomer", "pas": 1}, resultat))
        fil.start()
        cmd = noeud.receive_json()
        assert cmd["type"] == "commande" and cmd["commande"]["action"] == "zoomer" and cmd["commande"]["pas"] == 1
        noeud.send_json({"type": "reponse", "id": cmd["id"], "cadrage": {"zoom": 1.25}})
        fil.join(5)
        assert resultat["r"].status_code == 200 and resultat["r"].json() == {"zoom": 1.25}
        assert client.get("/api/cadrage/cible").json() == {"connecte": True, "cadrage": {"zoom": 1.25}}
        assert client.get("/api/etat").json()["cadrages"]["cible"]["zoom"] == 1.25

        # Le nœud refuse : erreur 400 pour la télécommande
        resultat = {}
        fil = threading.Thread(target=commander, args=({"action": "deplacer", "dx": 1}, resultat))
        fil.start()
        cmd = noeud.receive_json()
        assert cmd["commande"] == {"action": "deplacer", "dx": 1, "dy": 0}
        noeud.send_json({"type": "reponse", "id": cmd["id"], "erreur": "caméra arrêtée"})
        fil.join(5)
        assert resultat["r"].status_code == 400

    attendre(client, lambda e: not e["cadrages"]["cible"]["connecte"])
    assert client.post("/api/cadrage/cible", json={"action": "reinitialiser"}).status_code == 503


def test_noeud_inconnu_refuse(client):
    with client.websocket_connect("/api/noeud/ws?camera=inconnue") as noeud:
        with pytest.raises(Exception):
            noeud.receive_json()


def test_score_masque_sans_detection(client):
    main.serveur.config.cameras[1].detection = False
    e = client.get("/api/etat").json()
    assert e["score_actif"] is False and "groupements" not in e and "blason" not in e
    assert client.post("/api/impact", json={"x_mm": 1, "y_mm": 2}).status_code == 404
    assert client.post("/api/commande", json={"action": "score", "valeur": 9}).status_code == 404
    # Le reste fonctionne : tir, rejeu
    assert client.post("/api/lacher", json={}).status_code == 200
    vues = {c["id"]: c for c in e["cameras"]}
    assert vues["cible"]["direct"] and not vues["profil"]["direct"]


def test_wifi_et_adresse_publique(client):
    e = client.get("/api/etat").json()
    assert e["wifi"] == {"ssid": "ArcReplay", "mot_de_passe": "arc;2026"}
    assert e["adresse_publique"] == "http://10.42.0.1"
    cadrables = {c["id"]: c["cadrage"] for c in e["cameras"]}
    assert cadrables["cible"]["pas_zoom"] == 1.25 and cadrables["profil"] is None
    assert e["score_actif"] is True
