import { dureeAGarder, indiceDansClip, Tampon } from "./tampon";
import { DetecteurLacher, niveauDbfs } from "./son";

export const QUALITES = {
  economie: { largeur: 640, jpeg: 0.6, libelle: "Économe (640 px)" },
  standard: { largeur: 960, jpeg: 0.7, libelle: "Standard (960 px)" },
  haute: { largeur: 1280, jpeg: 0.75, libelle: "Haute (1280 px)" },
};

export const CLIP = { avant_s: 6, apres_s: 3 };
const IPS_MAX = 30;
const ENCODAGES_MAX = 3; // au-delà, on saute une image plutôt que de prendre du retard

/**
 * Tout ce qui tourne en continu, hors de React : caméra, encodage JPEG des images,
 * affichage en différé ou en rejeu, écoute du micro.
 *
 * Fonctionne pareil sur Safari (iPad), Chrome (Android) et les navigateurs de PC :
 * on n'utilise que getUserMedia, canvas, toBlob et createImageBitmap.
 */
export class Moteur {
  constructor({ onLacher, onNiveau } = {}) {
    this.onLacher = onLacher;
    this.onNiveau = onNiveau;
    this.tampon = new Tampon();
    this.delai_s = 10;
    this.detecteur = new DetecteurLacher(-20, 2000);
    this.microActif = true;
    this.scenes = []; // [{ canvas, couches: [{ images? }] }] ; sans images = direct
    this.rejeu = null; // { origine, decalage, vitesse, pause }
    this.dessins = new WeakMap(); // canvas -> clé de la dernière image dessinée
    this.ips = 0;
    this._fini = false;
  }

  // --- démarrage ---------------------------------------------------------------

  async demarrer({ camera = "user", qualite = "standard", micro = true }) {
    this.arreterFlux();
    this._fini = false;
    this.qualite = QUALITES[qualite] ?? QUALITES.standard;
    const video = camera === "user" || camera === "environment"
      ? { facingMode: { ideal: camera } }
      : { deviceId: { exact: camera } };
    Object.assign(video, { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30 } });
    const audio = micro
      ? { echoCancellation: false, noiseSuppression: false, autoGainControl: false }
      : false;
    try {
      this.flux = await navigator.mediaDevices.getUserMedia({ video, audio });
    } catch (e) {
      if (!micro) throw e;
      // Micro refusé ou absent : on continue sans, avec le bouton « Marquer »
      this.flux = await navigator.mediaDevices.getUserMedia({ video, audio: false });
    }

    this.video = document.createElement("video");
    Object.assign(this.video, { muted: true, playsInline: true, autoplay: true });
    this.video.setAttribute("playsinline", "");
    this.video.srcObject = this.flux;
    await this.video.play();

    this.encodeur = document.createElement("canvas");
    this.encodeurCtx = this.encodeur.getContext("2d");
    this.enCours = 0;
    this.derniereCapture = 0;
    this._capturer();
    if (this.flux.getAudioTracks().length) this._ecouter();
    this._boucleAffichage();
    return { micro: this.flux.getAudioTracks().length > 0 };
  }

  arreterFlux() {
    this._fini = true;
    clearInterval(this._minuteurCapture);
    clearInterval(this._minuteurSon);
    cancelAnimationFrame(this._raf);
    this.flux?.getTracks().forEach((p) => p.stop());
    this.audio?.close().catch(() => {});
    this.flux = null;
    this.audio = null;
  }

  arreter() {
    this.arreterFlux();
    this.tampon = new Tampon();
  }

  // --- capture -----------------------------------------------------------------

  _capturer() {
    const v = this.video;
    const image = () => {
      if (this._fini) return;
      const t = performance.now();
      if (t - this.derniereCapture >= 1000 / IPS_MAX - 4 && this.enCours < ENCODAGES_MAX && v.videoWidth) {
        this.derniereCapture = t;
        const largeur = Math.min(this.qualite.largeur, v.videoWidth);
        const hauteur = Math.round((largeur * v.videoHeight) / v.videoWidth);
        if (this.encodeur.width !== largeur) {
          this.encodeur.width = largeur;
          this.encodeur.height = hauteur;
        }
        this.encodeurCtx.drawImage(v, 0, 0, largeur, hauteur);
        this.enCours++;
        this.encodeur.toBlob((blob) => {
          this.enCours--;
          if (blob && !this._fini) this.tampon.ajouter(t, blob);
        }, "image/jpeg", this.qualite.jpeg);
        this._compterImage(t);
        this.tampon.purger(t - dureeAGarder({ delai_s: this.delai_s, ...CLIP }));
      }
      if ("requestVideoFrameCallback" in v) v.requestVideoFrameCallback(image);
    };
    if ("requestVideoFrameCallback" in v) v.requestVideoFrameCallback(image);
    else this._minuteurCapture = setInterval(image, 1000 / IPS_MAX);
  }

  _compterImage(t) {
    this._images = (this._images ?? []).filter((x) => t - x < 1000);
    this._images.push(t);
    this.ips = this._images.length;
  }

  // --- micro -------------------------------------------------------------------

  _ecouter() {
    const Contexte = window.AudioContext || window.webkitAudioContext;
    this.audio = new Contexte();
    this.audio.resume().catch(() => {});
    const source = this.audio.createMediaStreamSource(this.flux);
    const analyse = this.audio.createAnalyser();
    analyse.fftSize = 2048;
    source.connect(analyse);
    const bloc = new Float32Array(analyse.fftSize);
    let maxi = -120;
    let dernierEnvoi = 0;
    this._minuteurSon = setInterval(() => {
      analyse.getFloatTimeDomainData(bloc);
      const niveau = niveauDbfs(bloc);
      const t = performance.now();
      maxi = Math.max(maxi, niveau);
      if (t - dernierEnvoi > 150) {
        this.onNiveau?.(maxi);
        maxi = -120;
        dernierEnvoi = t;
      }
      // Le bloc couvre les ~40 dernières ms : on date le lâcher au milieu
      if (this.microActif && this.detecteur.bloc(niveau, t)) this.onLacher?.(t - 20);
    }, 20);
  }

  // --- affichage -----------------------------------------------------------------

  /** Écrans à dessiner. Une couche sans `images` montre le direct en différé. */
  afficher(scenes) {
    this.scenes = scenes;
    this.dessins = new WeakMap();
  }

  lancerRejeu(vitesse = 1) {
    this.rejeu = { origine: performance.now(), decalage: 0, vitesse, pause: false };
  }

  ecouleRejeu() {
    const r = this.rejeu;
    if (!r) return 0;
    return r.pause ? r.decalage : r.decalage + (performance.now() - r.origine) * r.vitesse;
  }

  reglerRejeu({ vitesse, pause, recommencer }) {
    if (!this.rejeu) return;
    const ecoule = recommencer ? 0 : this.ecouleRejeu();
    this.rejeu = {
      origine: performance.now(),
      decalage: ecoule,
      vitesse: vitesse ?? this.rejeu.vitesse,
      pause: pause ?? (recommencer ? false : this.rejeu.pause),
    };
  }

  arreterRejeu() {
    this.rejeu = null;
  }

  _boucleAffichage() {
    const tour = () => {
      if (this._fini) return;
      const cible = performance.now() - this.delai_s * 1000;
      const ecoule = this.ecouleRejeu();
      for (const scene of this.scenes) {
        const images = scene.couches.map((c) => {
          if (!c.images) return this.tampon.aLHeure(cible);
          const i = indiceDansClip(c.images, ecoule);
          return i < 0 ? null : c.images[i];
        });
        if (images.some((im) => !im)) continue;
        const cle = images.map((im) => im.t).join("|");
        if (this.dessins.get(scene.canvas) === cle) continue;
        this.dessins.set(scene.canvas, cle);
        dessiner(scene.canvas, images, cle, this.dessins);
      }
      this._raf = requestAnimationFrame(tour);
    };
    this._raf = requestAnimationFrame(tour);
  }
}

/** Décode les JPEG et les dessine (la seconde couche en transparence). */
async function dessiner(canvas, images, cle, dessins) {
  let cartes;
  try {
    cartes = await Promise.all(images.map((im) => createImageBitmap(im.blob)));
  } catch {
    return;
  }
  // Une image plus récente a pu être demandée entre-temps
  if (dessins.get(canvas) === cle) {
    const { width, height } = cartes[0];
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    const ctx = canvas.getContext("2d");
    cartes.forEach((carte, i) => {
      ctx.globalAlpha = i === 0 ? 1 : 0.5;
      ctx.drawImage(carte, 0, 0, width, height);
    });
    ctx.globalAlpha = 1;
  }
  cartes.forEach((c) => c.close?.());
}

/** Format vidéo que ce navigateur sait enregistrer (MP4 sur Safari, souvent WebM ailleurs). */
export function formatVideo() {
  if (typeof MediaRecorder === "undefined") return null;
  const formats = ["video/mp4;codecs=avc1", "video/mp4", "video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"];
  return formats.find((f) => MediaRecorder.isTypeSupported?.(f)) ?? null;
}

/**
 * Fabrique un fichier vidéo à partir des images d'un clip, en temps réel
 * (la durée du clip). `progression(0..1)` suit l'avancement.
 */
export async function clipEnVideo(images, progression) {
  const format = formatVideo();
  if (!format || !images.length) throw new Error("L'enregistrement vidéo n'est pas disponible sur ce navigateur.");
  const premiere = await createImageBitmap(images[0].blob);
  const canvas = document.createElement("canvas");
  canvas.width = premiere.width;
  canvas.height = premiere.height;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(premiere, 0, 0);
  premiere.close?.();
  if (!canvas.captureStream) throw new Error("L'enregistrement vidéo n'est pas disponible sur ce navigateur.");

  const flux = canvas.captureStream(IPS_MAX);
  const enregistreur = new MediaRecorder(flux, { mimeType: format, videoBitsPerSecond: 4_000_000 });
  const morceaux = [];
  enregistreur.ondataavailable = (e) => e.data.size && morceaux.push(e.data);
  const fin = new Promise((ok) => (enregistreur.onstop = ok));
  enregistreur.start(500);

  const debut = performance.now();
  const t0 = images[0].t;
  for (let i = 0; i < images.length; i++) {
    const carte = await createImageBitmap(images[i].blob);
    const attente = images[i].t - t0 - (performance.now() - debut);
    if (attente > 0) await new Promise((ok) => setTimeout(ok, attente));
    ctx.drawImage(carte, 0, 0, canvas.width, canvas.height);
    carte.close?.();
    progression?.(i / images.length);
  }
  await new Promise((ok) => setTimeout(ok, 100));
  enregistreur.stop();
  await fin;
  flux.getTracks().forEach((p) => p.stop());
  const type = format.split(";")[0];
  return new File(morceaux, `clip.${type === "video/mp4" ? "mp4" : "webm"}`, { type });
}

/** Partage (iPad, Android : « Enregistrer dans Fichiers / Photos ») ou téléchargement (PC). */
export async function remettreFichier(fichier, nom) {
  const f = new File([fichier], nom, { type: fichier.type });
  if (navigator.canShare?.({ files: [f] })) {
    try {
      await navigator.share({ files: [f], title: nom });
      return;
    } catch (e) {
      if (e?.name === "AbortError") return;
    }
  }
  const url = URL.createObjectURL(f);
  const a = document.createElement("a");
  a.href = url;
  a.download = nom;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
