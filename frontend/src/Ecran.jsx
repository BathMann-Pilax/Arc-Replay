import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { camerasVisibles, estMiroir, useEtat } from "./api";
import MiniCible from "./MiniCible";
import Rejeu from "./Rejeu";
import Telecommande from "./Telecommande";
import VueLive from "./VueLive";

function colonnesPour(n) {
  if (n <= 1) return 1;
  if (n <= 4) return 2;
  return 3;
}

function CodeTelecommande() {
  const [image, setImage] = useState(null);
  const adresse = `${location.origin}/telecommande`;
  useEffect(() => {
    QRCode.toDataURL(adresse, { margin: 1, width: 220 }).then(setImage);
  }, [adresse]);
  if (!image) return null;
  return (
    <div className="qr">
      <img src={image} alt="QR code de la télécommande" />
      <span>Télécommande</span>
      <small>{adresse}</small>
    </div>
  );
}

export default function Ecran() {
  const { etat, connecte, decalage } = useEtat();
  const controles = new URLSearchParams(location.search).has("controles");
  const [tiroir, setTiroir] = useState(false);

  if (!etat) return <div className="ecran ecran--vide">Connexion au serveur…</div>;

  const cameras = camerasVisibles(etat);
  const focus = cameras.find((c) => c.id === etat.disposition.focus);
  const voleeEnCours = etat.fleches.filter((f) => f.volee === etat.volee);
  const impacts = voleeEnCours.map((f) => f.impact).filter(Boolean);
  const derniere = etat.fleches.at(-1);

  const vue = (c, etiquette = true) => (
    <VueLive key={c.id} camera={c} delai={etat.delai_s} decalage={decalage}
      miroir={estMiroir(c, etat)} etiquette={etiquette} />
  );

  return (
    <div className="ecran">
      {etat.rejeu ? (
        <Rejeu etat={etat} />
      ) : focus ? (
        <div className="mosaique mosaique--focus">
          <div className="mosaique__principale">{vue(focus)}</div>
          <div className="mosaique__bande">{cameras.filter((c) => c !== focus).map((c) => vue(c))}</div>
        </div>
      ) : cameras.length ? (
        <div className="mosaique" style={{ gridTemplateColumns: `repeat(${colonnesPour(cameras.length)}, 1fr)` }}>
          {cameras.map((c) => vue(c))}
        </div>
      ) : (
        <div className="ecran--vide">Aucune caméra affichée</div>
      )}

      <div className="hud">
        <span className={`point ${connecte ? "point--ok" : ""}`} title={connecte ? "Connecté" : "Déconnecté"} />
        {!etat.rejeu && <span className="pastille pastille--forte">−{etat.delai_s} s</span>}
        <span className="hud__compteur">
          Volée {etat.volee} · Flèche {etat.fleche}
        </span>
        {etat.lateralite === "gaucher" && <span className="pastille">gaucher</span>}
        {etat.usb.presente && <span className="pastille">clé USB</span>}
      </div>

      {(impacts.length > 0 || derniere?.impact) && !etat.rejeu && (
        <div className="cible-hud">
          <MiniCible impacts={impacts} taille={140} />
          {derniere?.impact && (
            <div className="score score--grand">{derniere.impact.x ? "X" : derniere.impact.score}</div>
          )}
        </div>
      )}

      {etat.afficher_qr && !etat.rejeu && <CodeTelecommande />}

      {controles && (
        <>
          <button className="bouton bouton--flottant" onClick={() => setTiroir(!tiroir)}>
            {tiroir ? "Fermer" : "Commandes"}
          </button>
          {tiroir && (
            <div className="tiroir">
              <Telecommande integree />
            </div>
          )}
        </>
      )}
    </div>
  );
}
