import { useEffect, useState } from "react";

const PAS = 0.1; // un déplacement = un dixième de la zone affichée
const ZOOMS = [1, 1.5, 2, 3, 4, 6, 8];

/**
 * Cadrage d'une caméra « recadrage: true » (caméra HQ sur le pas de tir qui filme la cible).
 * Le nœud Raspberry Pi applique le réglage à son capteur en moins d'une seconde ;
 * l'aperçu se rafraîchit tout seul pour voir le résultat.
 */
export default function EditeurCadrage({ etat, agir }) {
  const cameras = etat.cameras.filter((c) => c.recadrage);
  const [camId, setCamId] = useState(cameras[0] && cameras[0].id);
  const [jeton, setJeton] = useState(Date.now());
  const [erreur, setErreur] = useState(false);

  // Aperçu rafraîchi toutes les 1,5 s
  useEffect(() => {
    const m = setInterval(() => setJeton(Date.now()), 1500);
    return () => clearInterval(m);
  }, []);

  if (!cameras.length) {
    return (
      <p className="info">
        Aucune caméra recadrable. Ajoutez <code>recadrage: true</code> à la caméra de cible dans la configuration.
      </p>
    );
  }
  const r = (etat.recadrages && etat.recadrages[camId]) || { zoom: 1, x: 0.5, y: 0.5 };
  const regler = (params) => agir("recadrage", { camera: camId, ...params });
  const zoomSuivant = (sens) => {
    const i = ZOOMS.findIndex((z) => z >= r.zoom - 0.01);
    const j = Math.min(ZOOMS.length - 1, Math.max(0, (i < 0 ? ZOOMS.length - 1 : i) + sens));
    regler({ zoom: ZOOMS[j] });
  };

  return (
    <div className="editeur-cadrage">
      {cameras.length > 1 && (
        <div className="rangee segments segments--defilant">
          {cameras.map((c) => (
            <button key={c.id} className={`bouton bouton--petit ${c.id === camId ? "bouton--actif" : ""}`}
              onClick={() => setCamId(c.id)}>
              {c.nom}
            </button>
          ))}
        </div>
      )}

      <div className="apercu">
        {!erreur && (
          <img src={`/api/apercu/${encodeURIComponent(camId)}?t=${jeton}`} alt={`Image de la caméra ${camId}`}
            onLoad={() => setErreur(false)} onError={() => setErreur(true)} />
        )}
      </div>
      {erreur && <p className="info info--erreur">Pas d'image : la caméra est-elle en ligne ?</p>}

      <div className="cadrage">
        <div className="cadrage__pave">
          <span />
          <button className="bouton" aria-label="Monter" onClick={() => regler({ dy: -PAS })}>↑</button>
          <span />
          <button className="bouton" aria-label="Gauche" onClick={() => regler({ dx: -PAS })}>←</button>
          <button className="bouton bouton--petit" onClick={() => regler({ centre_x: 0.5, centre_y: 0.5 })}>●</button>
          <button className="bouton" aria-label="Droite" onClick={() => regler({ dx: PAS })}>→</button>
          <span />
          <button className="bouton" aria-label="Descendre" onClick={() => regler({ dy: PAS })}>↓</button>
          <span />
        </div>
        <div className="cadrage__zoom">
          <button className="bouton" onClick={() => zoomSuivant(1)}>Zoom +</button>
          <strong>×{Number(r.zoom).toFixed(1)}</strong>
          <button className="bouton" onClick={() => zoomSuivant(-1)}>Zoom −</button>
          <button className="bouton bouton--discret" onClick={() => regler({ reinitialiser: true })}>Image entière</button>
        </div>
      </div>
      <p className="info">
        À 18 m avec l'objectif de 25 mm, un zoom de ×3 environ cadre la cible et son entourage. Le réglage
        est gardé d'une séance à l'autre.
      </p>
    </div>
  );
}
