import Hls from "hls.js";
import { useEffect, useRef, useState } from "react";
import Reperes from "./Reperes";
import { lireWhep, strategie, webrtcDisponible } from "./whep";

const DELAI_PREMIERE_IMAGE_MS = 6000;

/**
 * Une caméra « direct: true » (la vue de la cible) : en direct, sans différé.
 *
 * WebRTC (WHEP) d'abord, latence inférieure à la seconde. S'il échoue (navigateur
 * trop ancien, port 8189 bloqué…), repli sur le HLS au bord du direct
 * (2 à 3 s de retard), et nouvel essai WebRTC toutes les 30 s.
 */
export default function VueDirecte({
  camera, etiquette = true, miroir = false, reperes = [], grille = false, compacte = false,
}) {
  const videoRef = useRef(null);
  const [statut, setStatut] = useState("connexion");
  const [mode, setMode] = useState(null); // "webrtc" | "hls"
  const [taille, setTaille] = useState(null);
  const lireTaille = (e) => setTaille([e.currentTarget.videoWidth, e.currentTarget.videoHeight]);

  useEffect(() => {
    const video = videoRef.current;
    let fini = false;
    let fermerWebrtc = null;
    let hls = null;
    let minuteur = null;
    let echecs = 0;
    let tentative = 0; // une tentative dépassée ne doit plus rien toucher

    const nettoyer = () => {
      clearTimeout(minuteur);
      if (fermerWebrtc) fermerWebrtc();
      fermerWebrtc = null;
      if (hls) hls.destroy();
      hls = null;
      video.srcObject = null;
      video.removeAttribute("src");
    };

    const lancerHls = (reessayerMs) => {
      setMode("hls");
      const source = `/hls/${camera.id}/index.m3u8`;
      if (Hls.isSupported()) {
        hls = new Hls({
          liveSyncDurationCount: 1, // au plus près du bord du direct
          liveMaxLatencyDurationCount: 3,
          maxLiveSyncPlaybackRate: 1.5,
          maxBufferLength: 4,
          backBufferLength: 2,
          manifestLoadingMaxRetry: 2,
        });
        hls.loadSource(source);
        hls.attachMedia(video);
        hls.on(Hls.Events.MANIFEST_PARSED, () => video.play().catch(() => {}));
        hls.on(Hls.Events.FRAG_BUFFERED, () => setStatut("ok"));
        hls.on(Hls.Events.ERROR, (_e, d) => {
          if (!d.fatal) return;
          setStatut("hors_ligne");
          nettoyer();
          minuteur = setTimeout(essayer, 3000);
        });
      } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
        video.src = source;
        video.addEventListener("playing", () => setStatut("ok"), { once: true });
        video.play().catch(() => {});
      } else {
        setStatut("incompatible");
        return;
      }
      if (reessayerMs) {
        minuteur = setTimeout(() => {
          echecs = 0;
          nettoyer();
          essayer();
        }, reessayerMs);
      }
    };

    const echec = () => {
      if (fini) return;
      tentative += 1;
      echecs += 1;
      nettoyer();
      setStatut("connexion");
      essayer();
    };

    const essayer = () => {
      if (fini) return;
      const s = strategie(echecs, webrtcDisponible());
      if (s.mode === "hls") {
        lancerHls(s.reessayerWebrtcMs);
        return;
      }
      setMode("webrtc");
      const n = ++tentative;
      const actuelle = () => !fini && n === tentative;
      minuteur = setTimeout(async () => {
        // Pas d'image au bout de quelques secondes : on considère l'essai raté
        const garde = setTimeout(() => actuelle() && echec(), DELAI_PREMIERE_IMAGE_MS);
        try {
          const fermer = await lireWhep(video, camera.id, {
            surImage: () => {
              if (!actuelle()) return;
              clearTimeout(garde);
              echecs = 0;
              setStatut("ok");
            },
            surEchec: () => {
              clearTimeout(garde);
              if (actuelle()) echec();
            },
          });
          if (actuelle()) fermerWebrtc = fermer;
          else fermer();
        } catch {
          clearTimeout(garde);
          if (actuelle()) echec();
        }
      }, s.attenteMs);
    };

    essayer();
    return () => {
      fini = true;
      nettoyer();
    };
  }, [camera.id]);

  return (
    <div className={`vue ${statut !== "ok" ? "vue--attente" : ""} ${compacte ? "vue--compacte" : ""}`}>
      <video
        ref={videoRef}
        className={miroir ? "video--miroir" : undefined}
        muted
        playsInline
        autoPlay
        onLoadedMetadata={lireTaille}
        onResize={lireTaille}
      />
      {taille && <Reperes largeur={taille[0]} hauteur={taille[1]} lignes={reperes} grille={grille} miroir={miroir} />}
      {etiquette && (
        <div className="vue__etiquette">
          {camera.nom}
          <span className="pastille pastille--direct" title={mode === "hls" ? "Direct (HLS, 2 à 3 s)" : "Direct (WebRTC)"}>
            Direct{mode === "hls" ? " ~" : ""}
          </span>
        </div>
      )}
      {statut !== "ok" && (
        <div className="vue__statut">
          {statut === "connexion" && "Connexion à la vue en direct…"}
          {statut === "hors_ligne" && "Caméra hors ligne, nouvel essai…"}
          {statut === "incompatible" && "Navigateur incompatible avec la vidéo en direct"}
        </div>
      )}
    </div>
  );
}
