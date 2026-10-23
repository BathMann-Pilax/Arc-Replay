"""Extraction des clips de chaque flèche depuis le serveur de relecture MediaMTX."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx

log = logging.getLogger("arc.clips")


def rfc3339(heure: datetime) -> str:
    return heure.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parametres(camera_id: str, debut: datetime, duree_s: float) -> dict:
    return {
        "path": camera_id,
        "start": rfc3339(debut),
        "duration": f"{duree_s:.3f}",
        "format": "mp4",
    }


async def extraire(
    client: httpx.AsyncClient,
    playback: str,
    camera_id: str,
    debut: datetime,
    duree_s: float,
    destination: Path,
) -> None:
    """Télécharge un clip MP4 standard (lisible partout) vers `destination`.

    Aucun réencodage : MediaMTX recolle les morceaux d'enregistrement.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporaire = destination.with_suffix(".part")
    async with client.stream(
        "GET", f"{playback}/get", params=parametres(camera_id, debut, duree_s), timeout=120
    ) as r:
        if r.status_code != 200:
            corps = (await r.aread()).decode(errors="replace")[:200]
            raise RuntimeError(f"relecture {camera_id} : HTTP {r.status_code} {corps}")
        with open(temporaire, "wb") as f:
            async for bloc in r.aiter_bytes(1 << 16):
                f.write(bloc)
    if temporaire.stat().st_size == 0:
        temporaire.unlink()
        raise RuntimeError(f"relecture {camera_id} : clip vide")
    temporaire.replace(destination)
    log.info("clip %s enregistré (%d ko)", destination.name, destination.stat().st_size // 1024)
