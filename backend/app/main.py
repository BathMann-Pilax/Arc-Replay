"""Back-end Arc Replay : état partagé, commandes, flèches, clips et sauvegarde sur clé USB.

Stockage : seule la volée en cours reste sur le serveur. Chaque volée terminée
part sur la clé USB de l'archer si elle est branchée, sinon elle est supprimée.
Le serveur est vidé à chaque démarrage et à chaque fin de séance.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import os
import secrets
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from . import apercu, clips, config as cfg, mediamtx, seance, usb
from .blason import Blason

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s")
log = logging.getLogger("arc")


class Serveur:
    """Détient l'état, le sauvegarde et le diffuse aux écrans et télécommandes."""

    def __init__(self, config: cfg.Config):
        self.config = config
        self.verrou = asyncio.Lock()
        self.clients: set[WebSocket] = set()
        self.taches: set[asyncio.Task] = set()
        self.verrou_archives = asyncio.Lock()  # une seule copie vers la clé à la fois
        self.cameras_telephone: list[cfg.Camera] = []  # ajoutées depuis /camera, pas dans le yaml
        self.usb = {"presente": False, "libre_go": None}
        self.sauvegarde = {"etat": "inactif", "message": ""}
        self.disque = {"libre_go": None}
        self.erreurs_cameras: list[str] = []
        # Nœuds Raspberry Pi connectés (canal de commande) et commandes en attente de réponse
        self.noeuds: dict[str, WebSocket] = {}
        self.cadrages: dict[str, dict] = {}  # cadrage effectif annoncé par chaque nœud
        self.attentes: dict[int, asyncio.Future] = {}
        self.numero_commande = 0
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

    def toutes_cameras(self) -> list[cfg.Camera]:
        return self.config.cameras + self.cameras_telephone

    # --- persistance -------------------------------------------------------------

    def _charger_etat(self) -> dict:
        """Chaque démarrage ouvre une séance neuve et vide le stockage local.

        Seuls les réglages d'affichage (retard, latéralité, disposition, QR)
        sont repris de la dernière fois.
        """
        fichier = self.donnees / "etat.json"
        etat = seance.etat_initial(self.config)
        if fichier.exists():
            try:
                ancien = json.loads(fichier.read_text(encoding="utf-8"))
                for cle in ("delai_s", "lateralite", "disposition", "afficher_qr", "qr_type",
                            "blason", "grille", "reperes"):
                    if cle in ancien:
                        etat[cle] = ancien[cle]
            except (OSError, ValueError, TypeError):
                log.warning("etat.json illisible, réglages par défaut")
        self.purger_local()
        seance.reconcilier_disposition(etat, self.toutes_cameras())
        return etat

    def purger_local(self, garder: Optional[str] = None) -> None:
        """Supprime les séances du serveur (sauf `garder`) et les vieux enregistrements bruts."""
        if self.seances.exists():
            for p in self.seances.iterdir():
                if p.name != garder:
                    shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
        if self.config.serveur.enregistrements:
            n = usb.purger_enregistrements(Path(self.config.serveur.enregistrements))
            if n:
                log.info("%d enregistrement(s) brut(s) supprimé(s)", n)

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
        (dossier / "groupements.csv").write_text(seance.contenu_csv_groupements(self.etat), encoding="utf-8")

    def ecrire_fiche_fleche(self, f: dict) -> None:
        if f.get("archivee"):
            return
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
        vue = {
            **self.etat,
            "cameras": [
                {
                    "id": c.id,
                    "nom": c.nom,
                    "type": c.type,
                    "fps": c.fps,
                    "ralenti": c.ralenti,
                    "direct": c.direct,
                    "cadrage": c.cadrage.model_dump() if c.cadrage else None,
                }
                for c in self.toutes_cameras()
            ],
            # Cadrage effectif de chaque caméra cadrable, et nœud connecté ou non
            "cadrages": {
                c.id: {"connecte": c.id in self.noeuds, **self.cadrages.get(c.id, {})}
                for c in self.config.cameras if c.cadrage
            },
            "score_actif": self.config.score_actif,
            "usb": {**self.usb, "sauvegarde": self.sauvegarde},
            "disque": {**self.disque, "alerte_go": self.config.serveur.alerte_espace_go},
            "code_requis": bool(self.config.serveur.code_telecommande),
            "wifi": (
                {"ssid": self.config.serveur.wifi_ssid, "mot_de_passe": self.config.serveur.wifi_mot_de_passe or ""}
                if self.config.serveur.wifi_ssid else None
            ),
            "adresse_publique": self.config.serveur.adresse_publique.rstrip("/"),
            "erreurs_cameras": self.erreurs_cameras,
            "clips_config": {"avant_s": self.config.clips.avant_s, "apres_s": self.config.clips.apres_s},
        }
        if self.config.score_actif:
            vue["groupements"] = seance.groupements(self.etat)
        else:
            # Détection désactivée (detection: false) : rien sur le score ni les impacts
            vue.pop("blason", None)
        return vue

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
        self.lancer(self.archiver())
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
        dossier = f["dossier"]
        # Fichiers temporaires propres à cette découpe : si la flèche est annulée et
        # qu'une autre reprend son numéro, les deux découpes ne se marchent pas dessus.
        jeton = uuid.uuid4().hex[:8]

        # Toutes les caméras en même temps : le rejeu est prêt plus tôt
        async def une_camera(client: httpx.AsyncClient, cam_id: str) -> Optional[str]:
            relatif = f"{dossier}/{seance.nom_clip(fleche_id, cam_id)}"
            try:
                await clips.extraire(
                    client, self.config.serveur.mediamtx_playback, cam_id, debut, duree,
                    self.seances / f"{relatif}.{jeton}.part",
                )
                return relatif
            except (httpx.HTTPError, RuntimeError, OSError) as e:
                log.warning("clip %s / %s : %s", fleche_id, cam_id, e)
                return None

        ids = [cam.id for cam in self.toutes_cameras()]
        async with httpx.AsyncClient() as client:
            resultats = await asyncio.gather(*(une_camera(client, i) for i in ids))
        reussis = {i: r for i, r in zip(ids, resultats) if r}

        async with self.verrou:
            f = seance.trouver_fleche(self.etat, fleche_id)
            if (f is None or self.etat["seance"]["id"] != seance_id
                    or f["dossier"] != dossier or f["heure"] != heure.isoformat()):
                # Flèche annulée ou séance terminée pendant la découpe
                for relatif in reussis.values():
                    (self.seances / f"{relatif}.{jeton}.part").unlink(missing_ok=True)
                return
            for relatif in reussis.values():
                os.replace(self.seances / f"{relatif}.{jeton}.part", self.seances / relatif)
            f["clips"] = reussis
            f["statut"] = "pret" if len(reussis) == len(ids) else ("partiel" if reussis else "erreur")
            self.ecrire_fiche_fleche(f)
            self.ecrire_fichiers_seance()
            await self.diffuser()
        await self.archiver()

    async def impact(self, demande: "DemandeImpact") -> dict:
        async with self.verrou:
            f = seance.fleche_pour_impact(self.etat, demande.fleche_id)
            if f is None:
                raise HTTPException(404, "aucune flèche à associer à cet impact")
            impact = {
                "x_mm": demande.x_mm,
                "y_mm": demande.y_mm,
                # Diamètre envoyé par le nœud cible, sinon celui du blason choisi
                "diametre_mm": demande.diametre_mm or seance.blason_de(self.etat).diametre_mm,
                "rayon_fleche_mm": demande.rayon_fleche_mm,
                "image": None,
            }
            seance.calculer_impact(self.etat, impact)
            if demande.score is not None:  # score imposé (saisie manuelle)
                impact.update(score=demande.score, x=bool(demande.x) and demande.score == 10,
                              doute=False, alternative=None, manuel=True)
            if demande.image_jpeg_b64 and not f.get("archivee"):
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
            seance.appliquer_regles_volee(self.etat, f["volee"])
            self.ecrire_fiche_fleche(f)
            self.ecrire_fichiers_seance()
            await self.diffuser()
            return f

    # --- stockage : volée en cours sur le serveur, le reste sur la clé ou nulle part --

    async def surveiller_stockage(self) -> None:
        while True:
            s = await asyncio.to_thread(
                usb.statut, self.config.serveur.usb_chemin, self.config.serveur.usb_verifier_montage
            )
            self.donnees.mkdir(parents=True, exist_ok=True)
            disque = {"libre_go": await asyncio.to_thread(usb.espace_libre_go, self.donnees)}
            if s != self.usb or disque != self.disque:
                if s["presente"] != self.usb["presente"]:
                    self.sauvegarde = {"etat": "inactif", "message": ""}
                self.usb, self.disque = s, disque
                await self.diffuser(sauver=False)
            await asyncio.sleep(2)

    def _copier_vers_cle(self, seance_id: str, volees: list[int]) -> tuple[int, int]:
        """Copie des volées et des récapitulatifs de la séance sur la clé (fil séparé)."""
        racine_locale = self.seances / seance_id
        destination = Path(self.config.serveur.usb_chemin) / "arc-replay" / seance_id
        sources = [self.seances / seance.dossier_volee(seance_id, v) for v in volees]
        copies, ignores = usb.exporter([s for s in sources if s.exists()], destination)
        for nom in ("seance.csv", "groupements.csv"):
            if (racine_locale / nom).exists():
                usb.copier_fichier(racine_locale / nom, destination / nom)
        os.sync()
        return copies, ignores

    async def archiver(self, toutes: bool = False, seance_id: Optional[str] = None) -> None:
        """Libère le serveur des volées terminées : copie sur la clé si elle est là, puis suppression.

        Sans clé, les fichiers sont simplement supprimés : seule la volée en cours
        reste disponible pour le rejeu.
        """
        async with self.verrou_archives:
            async with self.verrou:
                if seance_id and seance_id != self.etat["seance"]["id"]:
                    return
                seance_id = self.etat["seance"]["id"]
                volees = seance.volees_a_archiver(self.etat, toutes)
                if not volees:
                    return
                self.ecrire_fichiers_seance()
                # Le rejeu d'une volée qui part est fermé avant de supprimer ses fichiers
                for v in volees:
                    seance.marquer_archivee(self.etat, v)
                await self.diffuser()

            message = None
            if self.usb["presente"]:
                self.sauvegarde = {"etat": "en_cours", "message": "Enregistrement sur la clé…"}
                await self.diffuser(sauver=False)
                try:
                    await asyncio.to_thread(self._copier_vers_cle, seance_id, volees)
                    noms = ", ".join(f"V{v}" for v in volees)
                    message = {"etat": "ok", "message": f"Volée(s) {noms} enregistrée(s) sur la clé."}
                except OSError as e:
                    log.warning("copie vers la clé : %s", e)
                    message = {"etat": "erreur", "message": f"Volée(s) non enregistrée(s) : {e}"}
            for v in volees:
                shutil.rmtree(self.seances / seance.dossier_volee(seance_id, v), ignore_errors=True)
            if message:
                self.sauvegarde = message
            await self.diffuser(sauver=False)

    async def sauvegarder_maintenant(self) -> None:
        """Copie la volée en cours sur la clé sans l'effacer, pour pouvoir retirer la clé."""
        if not self.usb["presente"]:
            self.sauvegarde = {"etat": "erreur", "message": "Aucune clé USB détectée"}
            await self.diffuser(sauver=False)
            return
        async with self.verrou_archives:
            async with self.verrou:
                seance_id = self.etat["seance"]["id"]
                archivees = set(self.etat["volees_archivees"])
                volees = sorted({f["volee"] for f in self.etat["fleches"]} - archivees)
                self.ecrire_fichiers_seance()
            self.sauvegarde = {"etat": "en_cours", "message": "Enregistrement sur la clé…"}
            await self.diffuser(sauver=False)
            try:
                await asyncio.to_thread(self._copier_vers_cle, seance_id, volees)
                self.sauvegarde = {"etat": "ok", "message": "Tout est sur la clé. Vous pouvez la retirer."}
            except OSError as e:
                self.sauvegarde = {"etat": "erreur", "message": f"Échec de la copie : {e}"}
        await self.diffuser(sauver=False)

    async def fin_de_seance(self) -> None:
        """Range la séance (sur la clé si elle est là), vide le serveur et en ouvre une neuve."""
        await self.archiver(toutes=True)
        async with self.verrou:
            seance.nouvelle_seance(self.etat)
            self.purger_local(garder=self.etat["seance"]["id"])
            await self.diffuser()

    # --- configuration -------------------------------------------------------------

    async def appliquer_cameras(self) -> None:
        self.erreurs_cameras = await mediamtx.synchroniser(
            self.config.serveur.mediamtx_api, self.toutes_cameras()
        )
        await self.diffuser(sauver=False)

    async def recharger(self) -> None:
        nouvelle = cfg.charger()
        async with self.verrou:
            self.config = nouvelle
            seance.reconcilier_disposition(self.etat, self.toutes_cameras())
            await self.diffuser()
        await self.appliquer_cameras()
        # Les nœuds connectés reçoivent leurs nouveaux réglages
        for cam_id, ws in list(self.noeuds.items()):
            cam = self.config.camera(cam_id)
            if cam:
                try:
                    await ws.send_text(json.dumps({"type": "config", "camera": cam.config_noeud()}))
                except Exception:
                    pass

    # --- nœuds Raspberry Pi : cadrage ----------------------------------------------

    async def commander_noeud(self, cam_id: str, commande: dict, delai_s: float = 3) -> dict:
        """Envoie une commande au nœud et attend le cadrage effectif qu'il renvoie."""
        ws = self.noeuds.get(cam_id)
        if ws is None:
            raise HTTPException(503, f"le nœud de la caméra « {cam_id} » n'est pas connecté")
        self.numero_commande += 1
        numero = self.numero_commande
        attente = asyncio.get_running_loop().create_future()
        self.attentes[numero] = attente
        try:
            await ws.send_text(json.dumps({"type": "commande", "id": numero, "commande": commande}))
            reponse = await asyncio.wait_for(attente, delai_s)
        except asyncio.TimeoutError:
            raise HTTPException(504, "le nœud n'a pas répondu")
        except Exception as e:
            if isinstance(e, HTTPException):
                raise
            raise HTTPException(503, f"nœud injoignable : {e}")
        finally:
            self.attentes.pop(numero, None)
        if reponse.get("erreur"):
            raise HTTPException(400, f"cadrage refusé par le nœud : {reponse['erreur']}")
        self.cadrages[cam_id] = reponse.get("cadrage") or {}
        await self.diffuser(sauver=False)
        return self.cadrages[cam_id]


# --- modèles des requêtes ----------------------------------------------------------


class DemandeLacher(BaseModel):
    heure: Optional[datetime] = None  # par défaut : maintenant
    source: Literal["audio", "manuel", "capteur", "autre"] = "autre"


class DemandeImpact(BaseModel):
    fleche_id: Optional[str] = None
    x_mm: float = Field(ge=-2000, le=2000)  # repère : centre du blason, x vers la droite
    y_mm: float = Field(ge=-2000, le=2000)  # y vers le haut
    diametre_mm: Optional[float] = Field(None, gt=0, le=1300)  # absent : blason de la séance
    rayon_fleche_mm: float = Field(2.5, ge=0, le=10)
    score: Optional[int] = Field(None, ge=0, le=10)
    x: Optional[bool] = None
    image_jpeg_b64: Optional[str] = None


class DemandeCameraTelephone(BaseModel):
    nom: str = Field(min_length=1, max_length=40)


REPERES_MAX = 8  # lignes de repère par caméra


class Commande(BaseModel):
    action: Literal[
        "delai", "lateralite", "disposition", "focus", "qr",
        "rejeu", "rejeu_controle", "rejeu_fermer",
        "nouvelle_volee", "nouvelle_seance", "marquer", "annuler_fleche", "score",
        "comparer", "sauvegarder_usb",
        "blason", "grille", "repere_ajouter", "repere_supprimer",
    ]
    valeur: Optional[float | str | bool] = None
    ordre: Optional[list[str]] = None
    masquees: Optional[list[str]] = None
    miroir: Optional[list[str]] = None  # disposition : vues retournées en miroir
    blason: Optional[Blason] = None
    # Ligne de repère : x1, y1, x2, y2 entre 0 et 1 dans l'image de la caméra
    points: Optional[list[float]] = Field(None, min_length=4, max_length=4)
    index: Optional[int] = None  # repère à supprimer (absent : tous ceux de la caméra)
    camera: Optional[str] = None
    fleche_id: Optional[str] = None
    fleche_id_b: Optional[str] = None  # comparaison : seconde flèche
    superposer: Optional[bool] = None  # comparaison : superposées plutôt que côte à côte
    x: Optional[bool] = None  # saisie du score : X (10 intérieur)
    lecture: Optional[bool] = None
    vitesse: Optional[float] = Field(None, gt=0, le=2)
    redemarrer: bool = False


# --- application ---------------------------------------------------------------------

serveur: Optional[Serveur] = None


@asynccontextmanager
async def cycle_de_vie(app: FastAPI):
    global serveur
    serveur = Serveur(cfg.charger())
    serveur.lancer(serveur.appliquer_cameras())
    serveur.lancer(serveur.surveiller_stockage())
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


def verifier_code(x_arc_code: Optional[str] = Header(None)) -> None:
    """Si un code est configuré, la télécommande doit l'envoyer (en-tête X-Arc-Code)."""
    attendu = srv().config.serveur.code_telecommande
    if attendu and x_arc_code != attendu:
        raise HTTPException(403, "code de la télécommande requis")


@app.get("/api/sante")
async def sante():
    return {"ok": True, "cameras": len(srv().config.cameras), "erreurs_cameras": srv().erreurs_cameras}


@app.get("/api/etat")
async def lire_etat():
    return srv().vue()


@app.get("/api/apercu/{camera_id}")
async def apercu_camera(camera_id: str):
    """Image actuelle d'une caméra (JPEG), pour placer les repères depuis la télécommande."""
    s = srv()
    if camera_id not in [c.id for c in s.toutes_cameras()]:
        raise HTTPException(404, "caméra inconnue")
    try:
        image = await asyncio.to_thread(
            apercu.capturer, apercu.url_rtsp(s.config.serveur.mediamtx_api, camera_id))
    except Exception as e:  # caméra hors ligne, PyAV absent, flux illisible…
        log.warning("aperçu de %s impossible : %s", camera_id, e)
        raise HTTPException(503, "pas d'image : la caméra est-elle en ligne ?")
    return Response(image, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/api/cadrage/{camera_id}")
async def lire_cadrage(camera_id: str):
    s = srv()
    cam = s.config.camera(camera_id)
    if cam is None or cam.cadrage is None:
        raise HTTPException(404, "caméra sans cadrage (bloc « cadrage » dans la configuration)")
    return {"connecte": camera_id in s.noeuds, "cadrage": s.cadrages.get(camera_id)}


class DemandeCadrage(BaseModel):
    action: Literal["deplacer", "zoomer", "reinitialiser"]
    dx: float = Field(0, ge=-10, le=10)   # en pas (un pas = pas_deplacement de la largeur visible)
    dy: float = Field(0, ge=-10, le=10)
    pas: Optional[float] = Field(None, ge=-20, le=20)       # zoomer : +1 = zoom +, -1 = zoom −
    facteur: Optional[float] = Field(None, gt=0, le=16)     # zoomer : ou un facteur direct


@app.post("/api/cadrage/{camera_id}", dependencies=[Depends(verifier_code)])
async def cadrer(camera_id: str, demande: DemandeCadrage):
    """Relaye la commande au nœud ; tous les écrans et télécommandes reçoivent le nouveau cadrage."""
    s = srv()
    cam = s.config.camera(camera_id)
    if cam is None or cam.cadrage is None:
        raise HTTPException(404, "caméra sans cadrage (bloc « cadrage » dans la configuration)")
    commande = demande.model_dump(exclude_none=True)
    return await s.commander_noeud(camera_id, commande)


@app.websocket("/api/noeud/ws")
async def canal_noeud(ws: WebSocket, camera: str):
    """Canal ouvert par un nœud Raspberry Pi : réglages, commandes de cadrage, cadrage effectif."""
    s = srv()
    await ws.accept()
    cam = s.config.camera(camera)
    if cam is None:
        await ws.close(code=4404, reason="caméra inconnue dans arc-replay.yml")
        return
    precedent = s.noeuds.get(camera)
    s.noeuds[camera] = ws
    if precedent is not None:
        try:
            await precedent.close()
        except Exception:
            pass
    log.info("nœud « %s » connecté", camera)
    try:
        await ws.send_text(json.dumps({"type": "config", "camera": cam.config_noeud()}))
        await s.diffuser(sauver=False)
        while True:
            message = json.loads(await ws.receive_text())
            if message.get("type") == "cadrage":
                s.cadrages[camera] = message.get("cadrage") or {}
                await s.diffuser(sauver=False)
            elif message.get("type") == "reponse":
                attente = s.attentes.get(message.get("id"))
                if attente is not None and not attente.done():
                    attente.set_result(message)
    except (WebSocketDisconnect, ValueError):
        pass
    finally:
        if s.noeuds.get(camera) is ws:
            del s.noeuds[camera]
            log.info("nœud « %s » déconnecté", camera)
            await s.diffuser(sauver=False)


@app.post("/api/lacher")
async def lacher(demande: DemandeLacher):
    heure = (demande.heure or seance.maintenant()).astimezone()
    fleche = await srv().lacher(heure)
    if fleche is None:
        return {"ignore": True, "raison": "anti-rebond"}
    return fleche


SCORE_DESACTIVE = "score désactivé (detection: false dans la configuration)"


@app.post("/api/impact")
async def impact(demande: DemandeImpact):
    if not srv().config.score_actif:
        raise HTTPException(404, SCORE_DESACTIVE)
    return await srv().impact(demande)


@app.post("/api/recharger", dependencies=[Depends(verifier_code)])
async def recharger():
    try:
        await srv().recharger()
    except (OSError, ValidationError, ValueError) as e:
        raise HTTPException(400, f"configuration invalide : {e}")
    return {"ok": True, "erreurs_cameras": srv().erreurs_cameras}


@app.post("/api/cameras/telephone")
async def ajouter_camera_telephone(demande: DemandeCameraTelephone):
    """Ajoute une caméra publiée depuis le navigateur d'un téléphone (voir /camera)."""
    s = srv()
    cam = cfg.Camera(id=f"tel-{secrets.token_hex(3)}", nom=demande.nom.strip()[:40], type="reseau")
    erreurs = await mediamtx.synchroniser(s.config.serveur.mediamtx_api, [cam])
    if erreurs:
        raise HTTPException(502, erreurs[0])
    async with s.verrou:
        s.cameras_telephone.append(cam)
        s.etat["disposition"]["ordre"].append(cam.id)
        await s.diffuser()
    return {"id": cam.id}


@app.delete("/api/cameras/telephone/{cam_id}")
async def retirer_camera_telephone(cam_id: str):
    s = srv()
    async with s.verrou:
        s.cameras_telephone = [c for c in s.cameras_telephone if c.id != cam_id]
        e = s.etat
        e["disposition"]["ordre"] = [i for i in e["disposition"]["ordre"] if i != cam_id]
        e["disposition"]["masquees"] = [i for i in e["disposition"]["masquees"] if i != cam_id]
        e["disposition"]["miroir"] = [i for i in e["disposition"].get("miroir", []) if i != cam_id]
        if e["disposition"].get("focus") == cam_id:
            e["disposition"]["focus"] = None
        await s.diffuser()
    await mediamtx.supprimer_chemin(s.config.serveur.mediamtx_api, cam_id)
    return {"ok": True}


@app.post("/api/commande", dependencies=[Depends(verifier_code)])
async def commande(c: Commande):
    s = srv()
    if c.action in ("score", "blason") and not s.config.score_actif:
        raise HTTPException(404, SCORE_DESACTIVE)
    ids = [cam.id for cam in s.toutes_cameras()]

    if c.action == "marquer":
        heure = seance.maintenant() - timedelta(seconds=s.config.lacher.decalage_manuel_s)
        fleche = await s.lacher(heure)
        return fleche or {"ignore": True}

    if c.action == "sauvegarder_usb":
        s.lancer(s.sauvegarder_maintenant())
        return {"ok": True}

    if c.action == "nouvelle_seance":
        await s.fin_de_seance()
        return {"ok": True}

    async with s.verrou:
        e = s.etat
        if c.action == "delai":
            try:
                e["delai_s"] = min(float(cfg.DELAI_MAX_S), max(float(cfg.DELAI_MIN_S), float(c.valeur)))
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
            if c.miroir is not None:
                e["disposition"]["miroir"] = [i for i in c.miroir if i in ids]
        elif c.action == "focus":
            e["disposition"]["focus"] = c.camera if c.camera in ids else None
        elif c.action == "blason":
            if c.blason is None:
                raise HTTPException(400, "blason manquant")
            e["blason"] = c.blason.model_dump()
            seance.recalculer_scores(e)
            for f in e["fleches"]:
                if f.get("impact") and not f.get("archivee"):
                    s.ecrire_fiche_fleche(f)
            s.ecrire_fichiers_seance()
        elif c.action == "grille":
            if not isinstance(c.valeur, bool):
                raise HTTPException(400, "grille : true ou false")
            e["grille"] = c.valeur
        elif c.action == "repere_ajouter":
            if c.camera not in ids or c.points is None:
                raise HTTPException(400, "caméra et points (x1, y1, x2, y2) requis")
            if not all(0 <= p <= 1 for p in c.points):
                raise HTTPException(400, "points entre 0 et 1")
            liste = e.setdefault("reperes", {}).setdefault(c.camera, [])
            if len(liste) >= REPERES_MAX:
                raise HTTPException(409, f"{REPERES_MAX} repères au plus par caméra")
            liste.append([round(p, 4) for p in c.points])
        elif c.action == "repere_supprimer":
            liste = e.setdefault("reperes", {}).get(c.camera, [])
            if c.index is None:
                liste.clear()
            elif 0 <= c.index < len(liste):
                liste.pop(c.index)
            else:
                raise HTTPException(404, "repère introuvable")
        elif c.action == "qr":
            if isinstance(c.valeur, bool):
                e["afficher_qr"] = c.valeur
            elif c.valeur in ("telecommande", "camera"):
                e["qr_type"] = c.valeur
                e["afficher_qr"] = True
            else:
                raise HTTPException(400, "qr : valeur booléenne ou 'telecommande'/'camera'")
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
        elif c.action == "comparer":
            a = seance.trouver_fleche(e, c.fleche_id)
            b = seance.trouver_fleche(e, c.fleche_id_b) if c.fleche_id_b else None
            if a is None or b is None or a["id"] == b["id"]:
                raise HTTPException(404, "choisissez deux flèches différentes")
            communes = [i for i in ids if i in a["clips"] and i in b["clips"]]
            if not communes:
                raise HTTPException(409, "ces deux flèches n'ont pas de clip commun")
            camera = c.camera if c.camera in communes else (
                e["disposition"]["focus"] if e["disposition"]["focus"] in communes else communes[0])
            precedent = e["rejeu"] or {}
            e["rejeu"] = {
                "fleche_id": a["id"],
                "fleche_id_b": b["id"],
                "camera": camera,
                "superposer": bool(c.superposer),
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
            if c.superposer is not None and e["rejeu"].get("fleche_id_b"):
                e["rejeu"]["superposer"] = c.superposer
            if c.camera is not None and e["rejeu"].get("fleche_id_b"):
                if c.camera not in ids:
                    raise HTTPException(400, "caméra inconnue")
                e["rejeu"]["camera"] = c.camera
        elif c.action == "rejeu_fermer":
            e["rejeu"] = None
        elif c.action == "nouvelle_volee":
            seance.nouvelle_volee(e)
        elif c.action == "annuler_fleche":
            f = seance.annuler_derniere(e)
            if f is None:
                raise HTTPException(409, "aucune flèche à annuler dans la volée en cours")
            shutil.rmtree(s.seances / f["dossier"], ignore_errors=True)
            s.ecrire_fichiers_seance()
        elif c.action == "score":
            f = seance.trouver_fleche(e, c.fleche_id)
            if f is None:
                raise HTTPException(404, "aucune flèche à noter")
            try:
                valeur = int(c.valeur)
            except (TypeError, ValueError):
                raise HTTPException(400, "score invalide")
            if not 0 <= valeur <= 10:
                raise HTTPException(400, "score entre 0 et 10")
            f["impact"] = seance.impact_manuel(f, valeur, bool(c.x))
            seance.appliquer_regles_volee(e, f["volee"])
            s.ecrire_fiche_fleche(f)
            s.ecrire_fichiers_seance()
        await s.diffuser()
    if c.action == "nouvelle_volee":
        s.lancer(s.archiver())
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
