"""Création des chemins MediaMTX à partir de la liste des caméras."""

from __future__ import annotations

import asyncio
import logging

import httpx

from .config import Camera

log = logging.getLogger("arc.mediamtx")

SORTIE_RTSP = "-f rtsp -rtsp_transport tcp rtsp://localhost:$RTSP_PORT/$MTX_PATH"


def commande_ffmpeg_usb(cam: Camera) -> str:
    """Commande lancée par MediaMTX (runOnInit) pour une caméra USB.

    MediaMTX remplace lui-même $RTSP_PORT et $MTX_PATH.
    L'image clé est forcée toutes les secondes (-g fps) : c'est ce qui
    permet des segments HLS d'une seconde et des clips précis.
    """
    entree = (
        f"-f v4l2 -input_format {cam.format_entree} -framerate {cam.fps} "
        f"-video_size {cam.largeur}x{cam.hauteur} -i {cam.peripherique}"
    )
    g = cam.fps
    if cam.encodeur == "copy":
        encodage = "-c:v copy"
    elif cam.encodeur == "libx264":
        encodage = (
            f"-c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p "
            f"-g {g} -keyint_min {g} -sc_threshold 0 "
            f"-b:v {cam.debit} -maxrate {cam.debit} -bufsize {cam.debit}"
        )
    elif cam.encodeur == "vaapi":
        encodage = (
            "-vaapi_device /dev/dri/renderD128 -vf format=nv12,hwupload "
            f"-c:v h264_vaapi -g {g} -b:v {cam.debit}"
        )
    else:  # v4l2m2m (encodeur matériel du Pi 4)
        encodage = f"-c:v h264_v4l2m2m -pix_fmt yuv420p -g {g} -b:v {cam.debit}"
    return f"ffmpeg -hide_banner -loglevel warning -nostdin {entree} {encodage} {SORTIE_RTSP}"


def conf_chemin(cam: Camera) -> dict:
    """Configuration MediaMTX d'un chemin (l'enregistrement est dans pathDefaults)."""
    if cam.type == "usb":
        return {
            "source": "publisher",
            "runOnInit": commande_ffmpeg_usb(cam),
            "runOnInitRestart": True,
        }
    if cam.type == "rtsp":
        return {"source": cam.url}
    return {"source": "publisher"}  # nœud réseau qui publie vers le serveur


async def _appliquer(client: httpx.AsyncClient, api: str, cam: Camera) -> None:
    conf = conf_chemin(cam)
    existant = await client.get(f"{api}/v3/config/paths/get/{cam.id}")
    if existant.status_code == 200:
        r = await client.post(f"{api}/v3/config/paths/replace/{cam.id}", json=conf)
    else:
        r = await client.post(f"{api}/v3/config/paths/add/{cam.id}", json=conf)
    if r.status_code >= 400:
        raise RuntimeError(f"MediaMTX a refusé la caméra {cam.id} : {r.status_code} {r.text}")


async def supprimer_chemin(api: str, cam_id: str) -> None:
    """Retire un chemin ajouté dynamiquement (caméra d'un téléphone débranchée)."""
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            await client.post(f"{api}/v3/config/paths/delete/{cam_id}")
        except httpx.HTTPError as e:
            log.warning("suppression du chemin %s : %s", cam_id, e)


async def synchroniser(api: str, cameras: list[Camera], tentatives: int = 60) -> list[str]:
    """Crée ou met à jour un chemin par caméra. Attend que MediaMTX réponde.

    Renvoie la liste des erreurs (vide si tout va bien).
    """
    async with httpx.AsyncClient(timeout=5) as client:
        for essai in range(tentatives):
            try:
                await client.get(f"{api}/v3/paths/list")
                break
            except httpx.HTTPError:
                if essai == tentatives - 1:
                    return [f"MediaMTX injoignable sur {api}"]
                await asyncio.sleep(1)

        erreurs = []
        for cam in cameras:
            try:
                await _appliquer(client, api, cam)
                log.info("caméra %s configurée (%s)", cam.id, cam.type)
            except (httpx.HTTPError, RuntimeError) as e:
                log.error("%s", e)
                erreurs.append(str(e))
        return erreurs
