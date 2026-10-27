"""Vue en direct d'une caméra Raspberry Pi, recadrée depuis la télécommande.

Utilisé par le nœud cible en mode « cible directe » (`detection: false`) et par
le nœud caméra lancé avec --recadrage. Pas d'OpenCV, pas d'analyse d'image :
picamera2 → encodeur H.264 matériel → RTSP vers MediaMTX, et un canal
WebSocket pour les commandes de cadrage.

Au démarrage :
1. connexion au serveur, qui envoie les réglages de la caméra (config/arc-replay.yml) ;
   sans réponse sous 20 s, on garde les réglages locaux ;
2. démarrage de la caméra avec le cadrage enregistré (fichier JSON) ;
3. chaque commande est appliquée au capteur (ScalerCrop), enregistrée, et le
   cadrage effectif est renvoyé au serveur.
"""

from __future__ import annotations

import logging
import signal
import threading
import time
from pathlib import Path

from cadrage import Cadrage, Reglages, zone_maximale
from canal import Canal

log = logging.getLogger("arc.vue")

FICHIER_CADRAGE = "/var/lib/arc-replay/cadrage-cible.json"
# Réglages qui imposent de redémarrer la caméra s'ils changent
CLES_FLUX = ("capteur", "largeur", "hauteur", "fps", "debit")
DEFAUTS = {"capteur": "complet", "largeur": 1920, "hauteur": 1080, "fps": None, "debit": 6_000_000}


def parametres(locaux: dict, serveur: dict | None) -> dict:
    """Réglages du flux : ceux du serveur l'emportent sur ceux du fichier local."""
    p = {**DEFAUTS, **{k: v for k, v in locaux.items() if v is not None}}
    for cle in (*CLES_FLUX, "cadrage"):
        if serveur and serveur.get(cle) is not None:
            p[cle] = serveur[cle]
    if p["capteur"] not in ("complet", "binne"):
        p["capteur"] = "complet"
    # Pleine définition : 10 i/s sur la caméra HQ ; binné (2028 × 1520) : 30 i/s
    if not p.get("fps"):
        p["fps"] = 10 if p["capteur"] == "complet" else 30
    return p


def executer(locaux: dict) -> int:
    """Lance la vue cadrée ; rend la main quand le flux s'arrête (systemd relance)."""
    from streamer import demarrer_flux, flux_actif

    fichier = Path(locaux.get("fichier_cadrage") or FICHIER_CADRAGE)
    canal = Canal(locaux["serveur"], locaux["chemin"]).demarrer()
    distants = canal.attendre_config(20)
    if distants is None:
        log.warning("pas de réponse du serveur : réglages locaux")
    p = parametres(locaux, distants)
    reglages = Reglages.depuis(p.get("cadrage"), ratio=p["largeur"] / p["hauteur"])

    etat: dict = {}
    verrou = threading.Lock()

    def cadrage_initial(picam):
        # Zone maximale lue APRÈS la configuration (avant : (0, 0, 0, 0))
        c = Cadrage.charger(fichier, zone_maximale(picam), reglages)
        etat["cadrage"] = c
        log.info("cadrage restauré : zoom ×%.2f, zone %s", c.zoom, c.rectangle())
        return c.rectangle()

    picam, sortie = demarrer_flux(
        locaux["serveur"].split(":")[0],  # « 127.0.0.1:8080 » : RTSP reste sur le port 8554
        locaux["chemin"], p["largeur"], p["hauteur"], p["fps"], int(p["debit"]),
        capteur=p["capteur"], cadrage_initial=cadrage_initial,
    )

    def traiter(commande: dict) -> dict:
        with verrou:
            c: Cadrage = etat["cadrage"]
            c.appliquer(commande)
            picam.set_controls({"ScalerCrop": c.rectangle()})
            try:
                c.sauver(fichier)
            except OSError as e:
                log.warning("cadrage non enregistré (%s) : il sera perdu au redémarrage", e)
            return c.etat()

    arret = {"demande": False, "redemarrer": False}

    def sur_config(nouvelle: dict) -> None:
        nouveaux = parametres(locaux, nouvelle)
        if any(nouveaux[k] != p[k] for k in CLES_FLUX):
            log.info("réglages du flux modifiés : redémarrage de la caméra")
            arret["redemarrer"] = True
            return
        with verrou:
            c: Cadrage = etat["cadrage"]
            c.reglages = Reglages.depuis(nouveaux.get("cadrage"), ratio=p["largeur"] / p["hauteur"])
            c.zoomer(facteur=1)  # rebornage avec le nouveau zoom_max
            picam.set_controls({"ScalerCrop": c.rectangle()})
        canal.annoncer(c.etat())

    canal.traiter = traiter
    canal.sur_config = sur_config
    canal.annoncer(etat["cadrage"].etat())

    signal.signal(signal.SIGTERM, lambda *_: arret.update(demande=True))
    code = 0
    try:
        while not arret["demande"] and not arret["redemarrer"]:
            time.sleep(1)
            if not flux_actif(sortie):
                log.error("publication interrompue (serveur injoignable ?)")
                code = 1
                break
    except KeyboardInterrupt:
        pass
    finally:
        try:
            picam.stop_recording()
            picam.close()
        except Exception:
            pass
    return 3 if arret["redemarrer"] else code
