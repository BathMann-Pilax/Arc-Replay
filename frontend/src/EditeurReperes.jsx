import { useState } from "react";
import { angleRepere } from "./logique";
import Reperes from "./Reperes";

const borner = (v) => Math.min(1, Math.max(0, v));

/**
 * Lignes de repère d'une caméra, depuis la télécommande : on touche deux points
 * sur une image fixe de la caméra (/api/apercu), la ligne apparaît sur l'écran,
 * en direct comme en rejeu. Les points sont gardés en 0–1 dans l'image non
 * retournée, pour rester justes si on active ou coupe le miroir.
 */
export default function EditeurReperes({ etat, agir }) {
  const cameras = etat.cameras;
  const [camId, setCamId] = useState(etat.disposition.focus || (cameras[0] && cameras[0].id));
  const [jeton, setJeton] = useState(Date.now()); // change à chaque « nouvelle image »
  const [taille, setTaille] = useState(null);
  const [erreur, setErreur] = useState(false);
  const [premier, setPremier] = useState(null);

  if (!camId) return <p className="info">Aucune caméra configurée.</p>;
  const miroir = (etat.disposition.miroir || []).includes(camId);
  const lignes = (etat.reperes && etat.reperes[camId]) || [];

  const nouvelleImage = () => {
    setTaille(null);
    setErreur(false);
    setJeton(Date.now());
  };
  const choisir = (id) => {
    setCamId(id);
    setPremier(null);
    nouvelleImage();
  };
  const toucher = (e) => {
    if (!taille) return;
    const r = e.currentTarget.getBoundingClientRect();
    const xVu = borner((e.clientX - r.left) / r.width);
    const p = [miroir ? 1 - xVu : xVu, borner((e.clientY - r.top) / r.height)];
    if (!premier) {
      setPremier(p);
      return;
    }
    setPremier(null);
    agir("repere_ajouter", { camera: camId, points: premier.concat(p) });
  };

  return (
    <div className="editeur-reperes">
      <div className="rangee segments segments--defilant">
        {cameras.map((c) => (
          <button key={c.id} className={`bouton bouton--petit ${c.id === camId ? "bouton--actif" : ""}`}
            onClick={() => choisir(c.id)}>
            {c.nom}
          </button>
        ))}
      </div>

      <div className="apercu" onClick={toucher}>
        {!erreur && (
          <img src={`/api/apercu/${encodeURIComponent(camId)}?t=${jeton}`} alt={`Image de la caméra ${camId}`}
            className={miroir ? "video--miroir" : undefined}
            onLoad={(e) => setTaille([e.currentTarget.naturalWidth, e.currentTarget.naturalHeight])}
            onError={() => setErreur(true)} />
        )}
        {taille && <Reperes largeur={taille[0]} hauteur={taille[1]} lignes={lignes}
          grille={!!etat.grille} miroir={miroir} point={premier} />}
      </div>
      {erreur && <p className="info info--erreur">Pas d'image : la caméra est-elle en ligne ?</p>}
      {!erreur && !taille && <p className="info">Chargement de l'image…</p>}
      {taille && (
        <p className="info">
          {premier ? "Touchez le second point de la ligne." : "Touchez deux points de l'image pour tracer une ligne."}
        </p>
      )}

      {lignes.length > 0 && (
        <ul className="cameras">
          {lignes.map((l, i) => (
            <li key={i}>
              <span className="camera__nom">
                Ligne {i + 1}{taille && <small> · {angleRepere(l, taille[0], taille[1])}° avec l'horizontale</small>}
              </span>
              <button className="icone" aria-label={`Effacer la ligne ${i + 1}`}
                onClick={() => agir("repere_supprimer", { camera: camId, index: i })}>
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="rangee">
        <button className="bouton bouton--petit" onClick={nouvelleImage}>Nouvelle image</button>
        <button className="bouton bouton--petit" disabled={!lignes.length && !premier}
          onClick={() => {
            setPremier(null);
            if (lignes.length) agir("repere_supprimer", { camera: camId });
          }}>
          Tout effacer
        </button>
      </div>
    </div>
  );
}
