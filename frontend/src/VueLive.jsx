import Hls from "hls.js";
import { useEffect, useRef, useState } from "react";
import Reperes from "./Reperes";

/**
 * Une caméra en différé.
 *
 * Le retard est tenu par une boucle de recalage plutôt que par hls.js seul :
 * chaque seconde, on compare l'heure de l'image affichée (EXT-X-PROGRAM-DATE-TIME
 * fourni par MediaMTX) à « heure du serveur − délai ». Toutes les vues visent la
 * même heure, elles restent donc synchronisées entre elles.
 * Sans date dans le flux, on se rabat sur « bord du direct − délai ».
 */
export default function VueLive({
  camera, delai, decalage, etiquette = true, miroir = false, reperes = [], grille = false,
}) {
  const videoRef = useRef(null);
  const reglages = useRef({ delai, decalage });
  reglages.current = { delai, decalage };
  const [statut, setStatut] = useState("connexion");
  const [taille, setTaille] = useState(null); // taille réelle de l'image, pour les repères
  const lireTaille = (e) => setTaille([e.currentTarget.videoWidth, e.currentTarget.videoHeight]);

  useEffect(() => {
    const video = videoRef.current;
    const source = `/hls/${camera.id}/index.m3u8`;
    let hls = null;
    let relance = null;
    let fini = false;

    const demarrer = () => {
      if (fini) return;
      setStatut("connexion");
      if (Hls.isSupported()) {
        hls = new Hls({
          liveSyncDuration: reglages.current.delai,
          liveMaxLatencyDuration: 38,
          maxLiveSyncPlaybackRate: 1,
          lowLatencyMode: false,
          maxBufferLength: 40,
          backBufferLength: 10,
          manifestLoadingMaxRetry: 2,
        });
        hls.loadSource(source);
        hls.attachMedia(video);
        hls.on(Hls.Events.MANIFEST_PARSED, () => video.play().catch(() => {}));
        hls.on(Hls.Events.FRAG_BUFFERED, () => setStatut("ok"));
        hls.on(Hls.Events.ERROR, (_e, d) => {
          if (!d.fatal) return;
          setStatut("hors_ligne");
          hls.destroy();
          hls = null;
          relance = setTimeout(demarrer, 3000);
        });
      } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
        // Ancien Safari sans MSE : HLS natif (recalage par le bord du direct uniquement)
        video.src = source;
        video.addEventListener("playing", () => setStatut("ok"), { once: true });
        video.play().catch(() => {});
      } else {
        setStatut("incompatible");
      }
    };

    const recaler = () => {
      if (!video || video.readyState < 2 || video.seekable.length === 0) return;
      const { delai, decalage } = reglages.current;
      const debut = video.seekable.start(0);
      const fin = video.seekable.end(video.seekable.length - 1);
      let saut;
      const dateImage = hls?.playingDate;
      if (dateImage && !isNaN(dateImage.getTime())) {
        const cible = Date.now() + decalage - delai * 1000;
        saut = (cible - dateImage.getTime()) / 1000;
      } else {
        saut = fin - delai - video.currentTime;
      }
      if (Math.abs(saut) > 0.4) {
        video.currentTime = Math.min(fin - 0.3, Math.max(debut + 0.1, video.currentTime + saut));
      }
      if (video.paused) video.play().catch(() => {});
    };

    demarrer();
    const minuteur = setInterval(recaler, 1000);
    return () => {
      fini = true;
      clearInterval(minuteur);
      clearTimeout(relance);
      hls?.destroy();
      video.removeAttribute("src");
      video.load();
    };
  }, [camera.id]);

  return (
    <div className={`vue ${statut !== "ok" ? "vue--attente" : ""}`}>
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
          {camera.ralenti && <span className="pastille">{camera.fps} i/s</span>}
        </div>
      )}
      {statut !== "ok" && (
        <div className="vue__statut">
          {statut === "connexion" && "Connexion au flux…"}
          {statut === "hors_ligne" && "Caméra hors ligne, nouvel essai…"}
          {statut === "incompatible" && "Navigateur incompatible avec la vidéo en direct"}
        </div>
      )}
    </div>
  );
}
