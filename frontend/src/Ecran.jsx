import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { camerasVisibles, codeTelecommande, useEtat } from "./api";
import { adresseTelecommande, colonnesPour, libelleScore, origineVisible, texteQrWifi } from "./logique";
import MiniCible from "./MiniCible";
import Rejeu from "./Rejeu";
import Telecommande from "./Telecommande";
import VueLive from "./VueLive";

function Qr({ adresse, etiquette, texte }) {
  const [image, setImage] = useState(null);
  useEffect(() => {
    QRCode.toDataURL(adresse, { margin: 1, width: 220 }).then(setImage);
  }, [adresse]);
  if (!image) return null;
  return (
    <div className="qr">
      <img src={image} alt={`QR code : ${etiquette}`} />
      <span>{etiquette}</span>
      <small>{texte ?? adresse}</small>
    </div>
  );
}

function CodeTelecommande({ origine }) {
  // Si un code est configuré, ouvrir l'écran une fois avec ?code=… : le QR code le transmet
  const adresse = adresseTelecommande(origine, codeTelecommande());
  return <Qr adresse={adresse} etiquette="2. Télécommande" texte={`${origine}/telecommande`} />;
}

function CodeCamera({ origine }) {
  const adresse = `https://${new URL(origine).hostname}/camera`;
  return <Qr adresse={adresse} etiquette="2. Ajouter une caméra" />;
}

function CodeWifi({ wifi }) {
  return (
    <Qr adresse={texteQrWifi(wifi.ssid, wifi.mot_de_passe)} etiquette="1. Wi-Fi"
      texte={wifi.mot_de_passe ? `${wifi.ssid} · ${wifi.mot_de_passe}` : wifi.ssid} />
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
  const groupement = etat.groupements?.volee;
  const derniere = etat.fleches.at(-1);

  const vue = (c, etiquette = true) => (
    <VueLive key={c.id} camera={c} delai={etat.delai_s} decalage={decalage}
      etiquette={etiquette} miroir={(etat.disposition.miroir || []).includes(c.id)}
      reperes={etat.reperes?.[c.id] || []} grille={!!etat.grille} />
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
          <MiniCible impacts={impacts} groupement={groupement} blason={etat.blason} taille={140} />
          {derniere?.impact && (
            <div className="score score--grand">
              {libelleScore(derniere.impact)}
              {derniere.impact.doute && <span className="score__doute" title="Sur la ligne, à confirmer">?</span>}
            </div>
          )}
          {groupement && (
            <div className="cible-hud__groupement">Groupement · ⌀ {Math.round(groupement.dispersion_mm * 2)} mm</div>
          )}
        </div>
      )}

      {etat.afficher_qr && !etat.rejeu && (() => {
        const origine = origineVisible(location.origin, location.hostname, etat.adresse_publique);
        return (
          <div className="qrs">
            {etat.wifi && <CodeWifi wifi={etat.wifi} />}
            {etat.qr_type === "camera" ? <CodeCamera origine={origine} /> : <CodeTelecommande origine={origine} />}
          </div>
        );
      })()}

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
