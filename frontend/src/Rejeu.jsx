import { useEffect, useRef } from "react";
import { camerasVisibles, estMiroir, urlFichier } from "./api";

/**
 * Rejeu synchronisé d'une flèche : un clip par caméra, joués ensemble en boucle.
 * Piloté par la télécommande via etat.rejeu (lecture, vitesse, redémarrage).
 */
export default function Rejeu({ etat }) {
  const rejeu = etat.rejeu;
  const fleche = etat.fleches.find((f) => f.id === rejeu.fleche_id);
  const cameras = camerasVisibles(etat).filter((c) => fleche?.clips[c.id]);
  const videos = useRef({});

  const toutes = () => cameras.map((c) => videos.current[c.id]).filter(Boolean);

  // Vitesse et lecture/pause
  useEffect(() => {
    for (const v of toutes()) {
      v.playbackRate = rejeu.vitesse;
      if (rejeu.lecture) v.play().catch(() => {});
      else v.pause();
    }
  });

  // Redémarrage depuis le début (nouvelle flèche ou bouton « recommencer »)
  useEffect(() => {
    for (const v of toutes()) {
      v.currentTime = 0;
      if (rejeu.lecture) v.play().catch(() => {});
    }
  }, [rejeu.sequence, rejeu.fleche_id]);

  // Les vidéos dérivent un peu : on les recale sur la première
  useEffect(() => {
    const minuteur = setInterval(() => {
      const [maitre, ...autres] = toutes();
      if (!maitre) return;
      for (const v of autres) {
        if (Math.abs(v.currentTime - maitre.currentTime) > 0.12) v.currentTime = maitre.currentTime;
      }
    }, 400);
    return () => clearInterval(minuteur);
  });

  if (!fleche) return null;
  const colonnes = Math.ceil(Math.sqrt(cameras.length || 1));

  return (
    <div className="rejeu">
      <div className="rejeu__bandeau">
        <span className="rejeu__titre">Rejeu · Volée {fleche.volee} · Flèche {fleche.numero}</span>
        {fleche.impact && <span className="score">{fleche.impact.x ? "X" : fleche.impact.score}</span>}
        <span className="pastille pastille--forte">
          {rejeu.vitesse === 1 ? "vitesse réelle" : `ralenti ×${rejeu.vitesse}`}
        </span>
        {!rejeu.lecture && <span className="pastille">pause</span>}
      </div>
      <div className="mosaique" style={{ gridTemplateColumns: `repeat(${colonnes}, 1fr)` }}>
        {cameras.map((c) => (
          <div className="vue" key={c.id}>
            <video
              ref={(el) => (videos.current[c.id] = el)}
              src={urlFichier(fleche.clips[c.id])}
              muted
              playsInline
              loop
              autoPlay
              style={estMiroir(c, etat) ? { transform: "scaleX(-1)" } : undefined}
            />
            <div className="vue__etiquette">{c.nom}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
