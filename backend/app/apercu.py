"""Image fixe d'une caméra, pour placer les lignes de repère depuis la télécommande.

L'image est lue sur le flux RTSP de MediaMTX (première image clé), puis réduite et
encodée en JPEG avec PyAV : pas besoin de ffmpeg dans l'image du back-end.
"""

from __future__ import annotations

import time
from fractions import Fraction

import httpx

LARGEUR_MAX = 960  # suffisant pour viser deux points, léger sur le Wi-Fi


def url_rtsp(mediamtx_api: str, camera_id: str) -> str:
    """Même hôte que l'API de MediaMTX, port RTSP 8554 (voir mediamtx/mediamtx.yml)."""
    return f"rtsp://{httpx.URL(mediamtx_api).host}:8554/{camera_id}"


def capturer(url: str, delai_s: float = 6.0) -> bytes:
    import av  # import tardif : le reste du serveur fonctionne même sans PyAV

    limite = time.monotonic() + delai_s
    with av.open(url, options={"rtsp_transport": "tcp"}, timeout=delai_s) as conteneur:
        flux = conteneur.streams.video[0]
        cle_vue = False
        for paquet in conteneur.demux(flux):
            if time.monotonic() > limite:
                break
            # Avant la première image clé, le décodeur ne donne que des images incomplètes
            if not cle_vue and not paquet.is_keyframe:
                continue
            cle_vue = True
            for image in paquet.decode():
                return jpeg(image)
    raise RuntimeError("aucune image reçue")


def jpeg(image) -> bytes:
    import av

    if image.width > LARGEUR_MAX:
        hauteur = round(image.height * LARGEUR_MAX / image.width / 2) * 2
        image = image.reformat(width=LARGEUR_MAX, height=hauteur)
    image = image.reformat(format="yuvj420p")
    encodeur = av.CodecContext.create("mjpeg", "w")
    encodeur.width, encodeur.height = image.width, image.height
    encodeur.pix_fmt = "yuvj420p"
    encodeur.time_base = Fraction(1, 25)
    paquets = list(encodeur.encode(image)) + list(encodeur.encode(None))
    return bytes(paquets[0])
