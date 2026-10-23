import { useEffect, useRef } from "react";
import { camerasVisibles, urlFichier } from "./api";
import { colonnesPour, libelleScore } from "./logique";

/**
 * Rejeu synchronisé, piloté par la télécommande via etat.rejeu (lecture, vitesse, redémarrage).
 *
 * - Une flèche : un clip par caméra, joués ensemble en boucle.
 * - Comparaison (rejeu.fleche_id_b) : la même caméra pour deux flèches, côte à côte
 *   ou superposées en transparence. Chaque clip commence au même temps avant le lâcher,
 *   donc démarrer les deux à zéro les aligne sur le lâcher.
 */
export default function Rejeu({ etat }) {
  const rejeu = etat.rejeu;
  const fleche = etat.fleches.find((f) => f.id === rejeu.fleche_id);
  const flecheB = rejeu.fleche_id_b ? etat.fleches.find((f) => f.id === rejeu.fleche_id_b) : null;
  const videos = useRef({});

  // Liste des vidéos à jouer : [clé, flèche, caméra]
  let pistes;
  if (flecheB) {
    const cam = etat.cameras.find((c) => c.id === rejeu.camera);
    pistes = cam && fleche?.clips[cam.id] && flecheB.clips[cam.id]
      ? [["a", fleche, cam], ["b", flecheB, cam]]
      : [];
  } else {
    pistes = camerasVisibles(etat)
      .filter((c) => fleche?.clips[c.id])
      .map((c) => [c.id, fleche, c]);
  }

  const toutes = () => pistes.map(([cle]) => videos.current[cle]).filter(Boolean);

  // Vitesse et lecture/pause
  useEffect(() => {
    for (const v of toutes()) {
      v.playbackRate = rejeu.vitesse;
      if (rejeu.lecture) v.play().catch(() => {});
      else v.pause();
    }
  });

  // Redémarrage depuis le début (nouvelle flèche, nouvelle caméra ou bouton « recommencer »)
  useEffect(() => {
    for (const v of toutes()) {
      v.currentTime = 0;
      if (rejeu.lecture) v.play().catch(() => {});
    }
  }, [rejeu.sequence, rejeu.fleche_id, rejeu.fleche_id_b, rejeu.camera]);

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

  const video = ([cle, f, cam], style) => (
    <video
      key={cle}
      ref={(el) => (videos.current[cle] = el)}
      src={urlFichier(f.clips[cam.id])}
      muted
      playsInline
      loop
      autoPlay
      style={style}
    />
  );
  const nomFleche = (f) => `V${f.volee} F${f.numero}${f.impact ? ` · ${libelleScore(f.impact)}` : ""}`;

  let contenu;
  if (flecheB && rejeu.superposer && pistes.length === 2) {
    contenu = (
      <div className="mosaique">
        <div className="vue vue--superposee">
          {video(pistes[0])}
          {video(pistes[1], { opacity: 0.5 })}
          <div className="vue__etiquette">
            {pistes[0][2].nom} · <span className="legende legende--a">{nomFleche(fleche)}</span>
            {" + "}<span className="legende legende--b">{nomFleche(flecheB)}</span> (transparente)
          </div>
        </div>
      </div>
    );
  } else {
    const colonnes = flecheB ? 2 : colonnesPour(pistes.length);
    contenu = (
      <div className="mosaique" style={{ gridTemplateColumns: `repeat(${colonnes}, 1fr)` }}>
        {pistes.map((p) => (
          <div className="vue" key={p[0]}>
            {video(p)}
            <div className="vue__etiquette">{flecheB ? `${p[2].nom} · ${nomFleche(p[1])}` : p[2].nom}</div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="rejeu">
      <div className="rejeu__bandeau">
        <span className="rejeu__titre">
          {flecheB
            ? `Comparaison · ${nomFleche(fleche)} / ${nomFleche(flecheB)}`
            : `Rejeu · Volée ${fleche.volee} · Flèche ${fleche.numero}`}
        </span>
        {!flecheB && fleche.impact && <span className="score">{libelleScore(fleche.impact)}</span>}
        <span className="pastille pastille--forte">
          {rejeu.vitesse === 1 ? "vitesse réelle" : `ralenti ×${rejeu.vitesse}`}
        </span>
        {!rejeu.lecture && <span className="pastille">pause</span>}
      </div>
      {contenu}
    </div>
  );
}
