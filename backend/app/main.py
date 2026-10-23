"""Back-end Arc Replay : état partagé, commandes, flèches, clips et export USB."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import math
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Optional

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from . import clips, config as cfg, mediamtx, seance, usb

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s")
log = logging.getLogger("arc")


class Serveur:
    """Détient l'état, le sauvegarde et le diffuse aux écrans et télécommandes."""

    def __init__(self, config: cfg.Config):
        self.config = config
        self.verrou = asyncio.Lock()
        self.clients: set[WebSocket] = set()
        self.taches: set[asyncio.Task] = set()
        self.usb = {"presente": False, "libre_go": None}
        self.export = {"etat": "inactif", "message": "", "progression": 0}
        self.erreurs_cameras: list[str] = []
        self.etat = self._charger_etat()

    # --- chemins ---------------------------------------------------------------

    @property
    def donnees(self) -> Path:
        return Path(self.config.serveur.donnees)

    @property
    def seances(self) -> Path:
        return self.donnees / "seances"

    def dossier_seance(self) -> Path:
        return self.seances / self.etat["seance"]["id"]

    # --- persistance -------------------------------------------------------------

    def _charger_etat(self) -> dict:
        fichier = self.donnees / "etat.json"
        defaut = seance.etat_initial(self.config)
        etat = None
        if fichier.exists():
            try:
                etat = json.loads(fichier.read_text(encoding="utf-8"))
                for cle, valeur in defaut.items():
                    etat.setdefault(cle, valeur)
                # Séance commencée il y a plus de 6 h : on en ouvre une nouvelle
                debut = datetime.fromisoformat(etat["seance"]["debut"])
                if seance.maintenant() - debut > timedelta(hours=6):
                    seance.nouvelle_seance(etat)
            except (OSError, ValueError, KeyError, TypeError):
                log.warning("etat.json illisible, nouvel état")
                etat = None
        etat = etat or defaut
        etat["rejeu"] = None
        # Une flèche « en cours » au redémarrage ne sera jamais terminée
        for f in etat["fleches"]:
            if f["statut"] == "en_cours":
                f["statut"] = "erreur"
        seance.reconcilier_disposition(etat, self.config)
        return etat

    def _sauver(self) -> None:
        self.donnees.mkdir(parents=True, exist_ok=True)
        tmp = self.donnees / "etat.json.tmp"
        tmp.write_text(json.dumps(self.etat, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.donnees / "etat.json")

    def ecrire_fichiers_seance(self) -> None:
        dossier = self.dossier_seance()
        if not self.etat["fleches"]:
            return
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / "seance.csv").write_text(seance.contenu_csv(self.etat), encoding="utf-8")

    def ecrire_fiche_fleche(self, f: dict) -> None:
        dossier = self.seances / f["dossier"]
        dossier.mkdir(parents=True, exist_ok=True)
        fiche = {k: f[k] for k in ("id", "volee", "numero", "heure", "statut", "clips", "impact")}
        fiche["lateralite"] = self.etat["lateralite"]
        (dossier / "impact.json").write_text(
            json.dumps(fiche, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # --- diffusion ---------------------------------------------------------------

    def vue(self) -> dict:
        """État complet envoyé aux clients (avec les infos non sauvegardées)."""
        return {
            **self.etat,
            "cameras": [
                {
                    "id": c.id,
                    "nom": c.nom,
                    "type": c.type,
                    "fps": c.fps,
                    "miroir_gaucher": c.miroir_gaucher,
                    "ralenti": c.ralenti,
                }
                for c in self.config.cameras
            ],
            "usb": {**self.usb, "export": self.export},
            "erreurs_cameras": self.erreurs_cameras,
            "clips_config": {"avant_s": self.config.clips.avant_s, "apres_s": self.config.clips.apres_s},
        }

    async def diffuser(self, sauver: bool = True) -> None:
        if sauver:
            self._sauver()
        message = json.dumps(
            {"type": "etat", "etat": self.vue(), "heure_serveur": datetime.now().timestamp() * 1000},
            ensure_ascii=False,
        )
        morts = []
        for ws in list(self.clients):
            try:
                await ws.send_text(message)
            except Exception:  # client parti entre-temps
                morts.append(ws)
        for ws in morts:
            self.clients.discard(ws)

    def lancer(self, coro) -> None:
        tache = asyncio.create_task(coro)
        self.taches.add(tache)
        tache.add_done_callback(self.taches.discard)

    # --- flèches -----------------------------------------------------------------

    async def lacher(self, heure: datetime) -> Optional[dict]:
        async with self.verrou:
            fleche = seance.enregistrer_lacher(self.etat, self.config, heure)
            if fleche is None:
                return None
            self.ecrire_fichiers_seance()
            await self.diffuser()
        log.info("lâcher : flèche %s", fleche["id"])
        self.lancer(self.traiter_fleche(fleche["id"], heure, self.etat["seance"]["id"]))
        return fleche

    async def traiter_fleche(self, fleche_id: str, heure: datetime, seance_id: str) -> None:
        c = self.config.clips
        attente = (heure + timedelta(seconds=c.apres_s + c.marge_s) - seance.maintenant()).total_seconds()
        if attente > 0:
            await asyncio.sleep(attente)

        f = seance.trouver_fleche(self.etat, fleche_id)
        if f is None or self.etat["seance"]["id"] != seance_id:
            return  # séance changée entre-temps
        debut = heure - timedelta(seconds=c.avant_s)
        duree = c.avant_s + c.apres_s
        reussis, echecs = {}, []
        async with httpx.AsyncClient() as client:
            for cam in self.config.cameras:
                relatif = f"{f['dossier']}/{seance.nom_clip(fleche_id, cam.id)}"
                try:
                    await clips.extraire(
                        client, self.config.serveur.mediamtx_playback, cam.id, debut, duree,
                        self.seances / relatif,
                    )
                    reussis[cam.id] = relatif
                except (httpx.HTTPError, RuntimeError, OSError) as e:
                    log.warning("clip %s / %s : %s", fleche_id, cam.id, e)
                    echecs.append(cam.id)

        async with self.verrou:
            f = seance.trouver_fleche(self.etat, fleche_id)
            if f is None or self.etat["seance"]["id"] != seance_id:
                return
            f["clips"] = reussis
            f["statut"] = "pret" if not echecs else ("partiel" if reussis else "erreur")
            self.ecrire_fiche_fleche(f)
            self.ecrire_fichiers_seance()
            await self.diffuser()

    async def impact(self, demande: "DemandeImpact") -> dict:
        async with self.verrou:
            f = seance.fleche_pour_impact(self.etat, demande.fleche_id)
            if f is None:
                raise HTTPException(404, "aucune flèche à associer à cet impact")
            distance = math.hypot(demande.x_mm, demande.y_mm)
            score, est_x = seance.score_wa(distance, demande.diametre_mm, demande.rayon_fleche_mm)
            if demande.score is not None:  # score imposé (saisie manuelle)
                score, est_x = demande.score, bool(demande.x)
            impact = {
                "x_mm": demande.x_mm,
                "y_mm": demande.y_mm,
                "diametre_mm": demande.diametre_mm,
                "score": score,
                "x": est_x,
                "image": None,
            }
            if demande.image_jpeg_b64:
                try:
                    donnees = base64.b64decode(demande.image_jpeg_b64, validate=True)
                except (binascii.Error, ValueError):
                    raise HTTPException(400, "image_jpeg_b64 invalide")
                relatif = f"{f['dossier']}/{f['id']}_impact.jpg"
                chemin = self.seances / relatif
                chemin.parent.mkdir(parents=True, exist_ok=True)
                chemin.write_bytes(donnees)
                impact["image"] = relatif
            f["impact"] = impact
            self.ecrire_fiche_fleche(f)
            self.ecrire_fichiers_seance()
            await self.diffuser()
            return f

    # --- USB ---------------------------------------------------------------------

    async def surveiller_usb(self) -> None:
        while True:
            s = await asyncio.to_thread(
                usb.statut, self.config.serveur.usb_chemin, self.config.serveur.usb_verifier_montage
            )
            if s != self.usb:
                self.usb = s
                if not s["presente"] and self.export["etat"] == "termine":
                    self.export = {"etat": "inactif", "message": "", "progression": 0}
                await self.diffuser(sauver=False)
            await asyncio.sleep(2)

    async def exporter(self, portee: str) -> None:
        if self.export["etat"] == "en_cours":
            return
        if not self.usb["presente"]:
            self.export = {"etat": "erreur", "message": "Aucune clé USB détectée", "progression": 0}
            await self.diffuser(sauver=False)
            return
        if portee == "tout":
            sources = sorted(p for p in self.seances.iterdir() if p.is_dir()) if self.seances.exists() else []
        else:
            sources = [self.dossier_seance()] if self.dossier_seance().exists() else []
        if not sources:
            self.export = {"etat": "erreur", "message": "Rien à exporter pour l'instant", "progression": 0}
            await self.diffuser(sauver=False)
            return

        self.export = {"etat": "en_cours", "message": "Copie en cours…", "progression": 0}
        await self.diffuser(sauver=False)
        boucle = asyncio.get_running_loop()
        derniere = {"pct": -1}

        def progression(fait: int, total: int) -> None:
            pct = int(100 * fait / max(total, 1))
            if pct != derniere["pct"]:
                derniere["pct"] = pct
                self.export["progression"] = pct
                asyncio.run_coroutine_threadsafe(self.diffuser(sauver=False), boucle)

        destination = Path(self.config.serveur.usb_chemin) / "arc-replay"
        try:
            copies, ignores = await asyncio.to_thread(usb.exporter, sources, destination, progression)
            self.export = {
                "etat": "termine",
                "message": f"{copies} fichier(s) copié(s), {ignores} déjà présent(s). Vous pouvez retirer la clé.",
                "progression": 100,
            }
        except OSError as e:
            self.export = {"etat": "erreur", "message": f"Échec de la copie : {e}", "progression": 0}
        await self.diffuser(sauver=False)

    # --- configuration -------------------------------------------------------------

    async def appliquer_cameras(self) -> None:
        self.erreurs_cameras = await mediamtx.synchroniser(
            self.config.serveur.mediamtx_api, self.config.cameras
        )
        await self.diffuser(sauver=False)

    async def recharger(self) -> None:
        nouvelle = cfg.charger()
        async with self.verrou:
            self.config = nouvelle
            seance.reconcilier_disposition(self.etat, nouvelle)
            await self.diffuser()
        await self.appliquer_cameras()


# --- modèles des requêtes ----------------------------------------------------------


class DemandeLacher(BaseModel):
    heure: Optional[datetime] = None  # par défaut : maintenant
    source: Literal["audio", "manuel", "capteur", "autre"] = "autre"


class DemandeImpact(BaseModel):
    fleche_id: Optional[str] = None
    x_mm: float = Field(ge=-2000, le=2000)  # repère : centre du blason, x vers la droite
    y_mm: float = Field(ge=-2000, le=2000)  # y vers le haut
    diametre_mm: float = Field(1220, gt=0, le=1300)
    rayon_fleche_mm: float = Field(2.5, ge=0, le=10)
    score: Optional[int] = Field(None, ge=0, le=10)
    x: Optional[bool] = None
    image_jpeg_b64: Optional[str] = None


class Commande(BaseModel):
    action: Literal[
        "delai", "lateralite", "disposition", "focus", "qr",
        "rejeu", "rejeu_controle", "rejeu_fermer",
        "nouvelle_volee", "nouvelle_seance", "marquer", "export_usb",
    ]
    valeur: Optional[float | str | bool] = None
    ordre: Optional[list[str]] = None
    masquees: Optional[list[str]] = None
    camera: Optional[str] = None
    fleche_id: Optional[str] = None
    lecture: Optional[bool] = None
    vitesse: Optional[float] = Field(None, gt=0, le=2)
    redemarrer: bool = False
    portee: Literal["seance", "tout"] = "seance"


# --- application ---------------------------------------------------------------------

serveur: Optional[Serveur] = None


@asynccontextmanager
async def cycle_de_vie(app: FastAPI):
    global serveur
    serveur = Serveur(cfg.charger())
    serveur.lancer(serveur.appliquer_cameras())
    serveur.lancer(serveur.surveiller_usb())
    log.info("Arc Replay prêt : %d caméra(s)", len(serveur.config.cameras))
    yield
    for t in list(serveur.taches):
        t.cancel()


app = FastAPI(title="Arc Replay", lifespan=cycle_de_vie)

# En production, nginx sert /fichiers directement. Ce montage sert au développement.
app.mount(
    "/fichiers",
    StaticFiles(directory=Path(os.environ.get("ARC_DONNEES", "/data")) / "seances", check_dir=False),
    name="fichiers",
)


def srv() -> Serveur:
    assert serveur is not None
    return serveur


@app.get("/api/sante")
async def sante():
    return {"ok": True, "cameras": len(srv().config.cameras), "erreurs_cameras": srv().erreurs_cameras}


@app.get("/api/etat")
async def lire_etat():
    return srv().vue()


@app.post("/api/lacher")
async def lacher(demande: DemandeLacher):
    heure = (demande.heure or seance.maintenant()).astimezone()
    fleche = await srv().lacher(heure)
    if fleche is None:
        return {"ignore": True, "raison": "anti-rebond"}
    return fleche


@app.post("/api/impact")
async def impact(demande: DemandeImpact):
    return await srv().impact(demande)


@app.post("/api/recharger")
async def recharger():
    try:
        await srv().recharger()
    except (OSError, ValidationError, ValueError) as e:
        raise HTTPException(400, f"configuration invalide : {e}")
    return {"ok": True, "erreurs_cameras": srv().erreurs_cameras}


@app.post("/api/commande")
async def commande(c: Commande):
    s = srv()
    ids = [cam.id for cam in s.config.cameras]

    if c.action == "marquer":
        heure = seance.maintenant() - timedelta(seconds=s.config.lacher.decalage_manuel_s)
        fleche = await s.lacher(heure)
        return fleche or {"ignore": True}

    if c.action == "export_usb":
        s.lancer(s.exporter(c.portee))
        return {"ok": True}

    async with s.verrou:
        e = s.etat
        if c.action == "delai":
            try:
                e["delai_s"] = min(30.0, max(1.0, float(c.valeur)))
            except (TypeError, ValueError):
                raise HTTPException(400, "valeur de délai invalide")
        elif c.action == "lateralite":
            if c.valeur not in ("droitier", "gaucher"):
                raise HTTPException(400, "latéralité : droitier ou gaucher")
            e["lateralite"] = c.valeur
        elif c.action == "disposition":
            if c.ordre is not None:
                if sorted(c.ordre) != sorted(ids):
                    raise HTTPException(400, "l'ordre doit contenir chaque caméra une fois")
                e["disposition"]["ordre"] = c.ordre
            if c.masquees is not None:
                e["disposition"]["masquees"] = [i for i in c.masquees if i in ids]
        elif c.action == "focus":
            e["disposition"]["focus"] = c.camera if c.camera in ids else None
        elif c.action == "qr":
            e["afficher_qr"] = bool(c.valeur)
        elif c.action == "rejeu":
            f = seance.trouver_fleche(e, c.fleche_id)
            if f is None:
                raise HTTPException(404, "aucune flèche à rejouer")
            if not f["clips"]:
                raise HTTPException(409, "les clips de cette flèche ne sont pas encore prêts")
            precedent = e["rejeu"] or {}
            e["rejeu"] = {
                "fleche_id": f["id"],
                "lecture": True,
                "vitesse": c.vitesse or precedent.get("vitesse", 1.0),
                "sequence": precedent.get("sequence", 0) + 1,
            }
        elif c.action == "rejeu_controle":
            if e["rejeu"] is None:
                raise HTTPException(409, "aucun rejeu en cours")
            if c.lecture is not None:
                e["rejeu"]["lecture"] = c.lecture
            if c.vitesse is not None:
                e["rejeu"]["vitesse"] = c.vitesse
            if c.redemarrer:
                e["rejeu"]["sequence"] += 1
                e["rejeu"]["lecture"] = True
        elif c.action == "rejeu_fermer":
            e["rejeu"] = None
        elif c.action == "nouvelle_volee":
            seance.nouvelle_volee(e)
        elif c.action == "nouvelle_seance":
            seance.nouvelle_seance(e)
        await s.diffuser()
    return {"ok": True}


@app.websocket("/api/ws")
async def flux_etat(ws: WebSocket):
    s = srv()
    await ws.accept()
    s.clients.add(ws)
    try:
        await ws.send_text(json.dumps(
            {"type": "etat", "etat": s.vue(), "heure_serveur": datetime.now().timestamp() * 1000},
            ensure_ascii=False,
        ))
        while True:
            message = await ws.receive_text()
            if message == "ping":  # mesure de l'écart d'horloge par les clients
                await ws.send_text(json.dumps(
                    {"type": "pong", "heure_serveur": datetime.now().timestamp() * 1000}
                ))
    except WebSocketDisconnect:
        pass
    finally:
        s.clients.discard(ws)
