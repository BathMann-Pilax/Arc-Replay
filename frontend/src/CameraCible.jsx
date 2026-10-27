import { useEffect, useRef, useState } from "react";
import { cadrer } from "./api";
import VueDirecte from "./VueDirecte";

const DELAI_REPETITION_MS = 400; // maintien avant que la commande ne se répète
const PERIODE_REPETITION_MS = 180;

/**
 * Bouton qui répète son action tant qu'on le maintient appuyé.
 * Une seule commande à la fois vers le serveur : pas d'embouteillage si le
 * réseau est lent, la répétition attend la réponse précédente.
 */
function BoutonRepete({ action, children, className = "", ...props }) {
  const minuteurs = useRef([]);
  const enCours = useRef(false);
  const lancer = async () => {
    if (enCours.current) return;
    enCours.current = true;
    try {
      await action();
    } finally {
      enCours.current = false;
    }
  };
  const arreter = () => {
    minuteurs.current.forEach(clearTimeout);
    minuteurs.current.forEach(clearInterval);
    minuteurs.current = [];
  };
  useEffect(() => arreter, []);
  return (
    <button
      type="button"
      className={`bouton bouton--cadrage ${className}`}
      onPointerDown={(e) => {
        e.preventDefault();
        arreter();
        lancer();
        minuteurs.current.push(setTimeout(() => {
          minuteurs.current.push(setInterval(lancer, PERIODE_REPETITION_MS));
        }, DELAI_REPETITION_MS));
      }}
      onPointerUp={arreter}
      onPointerLeave={arreter}
      onPointerCancel={arreter}
      onContextMenu={(e) => e.preventDefault()}
      // Clavier (Entrée / Espace) : une commande par appui
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), lancer())}
      {...props}
    >
      {children}
    </button>
  );
}

/**
 * Section « Caméra cible » : miniature en direct et cadrage numérique, appliqué
 * par le nœud Raspberry Pi sur son capteur sans couper le flux.
 */
export default function CameraCible({ etat, surErreur }) {
  const cameras = etat.cameras.filter((c) => c.cadrage);
  const [camId, setCamId] = useState(cameras[0] && cameras[0].id);
  const camera = cameras.find((c) => c.id === camId) || cameras[0];
  if (!camera) return null;
  const cadrage = (etat.cadrages && etat.cadrages[camera.id]) || {};
  const connecte = !!cadrage.connecte;

  const envoyer = async (corps) => {
    try {
      await cadrer(camera.id, corps);
    } catch (e) {
      surErreur(e);
    }
  };
  const deplacer = (dx, dy) => () => envoyer({ action: "deplacer", dx, dy });
  const zoomer = (pas) => () => envoyer({ action: "zoomer", pas });

  return (
    <div className="camera-cible">
      {cameras.length > 1 && (
        <div className="rangee segments segments--defilant">
          {cameras.map((c) => (
            <button key={c.id} className={`bouton bouton--petit ${c.id === camera.id ? "bouton--actif" : ""}`}
              onClick={() => setCamId(c.id)}>
              {c.nom}
            </button>
          ))}
        </div>
      )}

      <div className="camera-cible__miniature">
        <VueDirecte key={camera.id} camera={camera} etiquette={false} compacte />
      </div>

      {!connecte && (
        <p className="info info--erreur">
          Le Raspberry Pi de la caméra cible n'est pas connecté : le cadrage est indisponible.
        </p>
      )}

      <div className="camera-cible__commandes">
        <div className="cadrage__pave">
          <span />
          <BoutonRepete aria-label="Monter" disabled={!connecte} action={deplacer(0, -1)}>▲</BoutonRepete>
          <span />
          <BoutonRepete aria-label="Gauche" disabled={!connecte} action={deplacer(-1, 0)}>◀</BoutonRepete>
          <span className="cadrage__zoom-valeur">×{Number(cadrage.zoom || 1).toFixed(2)}</span>
          <BoutonRepete aria-label="Droite" disabled={!connecte} action={deplacer(1, 0)}>▶</BoutonRepete>
          <span />
          <BoutonRepete aria-label="Descendre" disabled={!connecte} action={deplacer(0, 1)}>▼</BoutonRepete>
          <span />
        </div>
        <div className="cadrage__zoom">
          <BoutonRepete disabled={!connecte || cadrage.zoom >= (cadrage.zoom_max || 8)} action={zoomer(1)}>
            Zoom +
          </BoutonRepete>
          <BoutonRepete disabled={!connecte || !(cadrage.zoom > 1)} action={zoomer(-1)}>Zoom −</BoutonRepete>
          <button type="button" className="bouton bouton--cadrage" disabled={!connecte}
            onClick={() => envoyer({ action: "reinitialiser" })}>
            Vue complète
          </button>
        </div>
      </div>
      <p className="info">
        Maintenir une flèche appuyée pour déplacer en continu. Le cadrage est gardé sur le Raspberry Pi,
        même après un redémarrage.
      </p>
    </div>
  );
}
