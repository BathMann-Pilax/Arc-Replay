"""Détection des chemins perdus par MediaMTX (redémarré sans le back-end)."""

import asyncio

import httpx

from app import mediamtx
from app.config import Camera


def cameras() -> list[Camera]:
    return [Camera(id="profil", nom="Profil", type="reseau"),
            Camera(id="cible", nom="Cible", type="reseau")]


def manquants_avec(reponse) -> list[str] | None:
    async def appel():
        transport = httpx.MockTransport(reponse)
        async with httpx.AsyncClient(transport=transport) as client:
            return await mediamtx.chemins_manquants("http://mediamtx:9997", cameras(), client)
    return asyncio.run(appel())


def test_chemins_tous_presents():
    items = [{"name": "all_others"}, {"name": "profil"}, {"name": "cible"}]
    assert manquants_avec(lambda r: httpx.Response(200, json={"items": items})) == []


def test_chemins_perdus_apres_redemarrage_de_mediamtx():
    # MediaMTX relancé seul : il ne reste que les chemins de mediamtx.yml
    items = [{"name": "all_others"}]
    assert manquants_avec(lambda r: httpx.Response(200, json={"items": items})) == ["profil", "cible"]


def test_mediamtx_injoignable():
    def panne(requete):
        raise httpx.ConnectError("refusé", request=requete)
    assert manquants_avec(panne) is None
    assert manquants_avec(lambda r: httpx.Response(500, text="erreur")) is None
