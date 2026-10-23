import { useEffect, useRef, useState } from "react";
import { codeDepuisAdresse } from "./logique";

export { camerasVisibles, urlFichier } from "./logique";

/**
 * Abonnement à l'état partagé du serveur (WebSocket, reconnexion automatique).
 * Renvoie { etat, connecte, decalage } où `decalage` est l'écart d'horloge
 * serveur − appareil en millisecondes (la tablette n'a souvent pas l'heure
 * exacte sur un réseau sans internet).
 */
export function useEtat() {
  const [etat, setEtat] = useState(null);
  const [connecte, setConnecte] = useState(false);
  const [decalage, setDecalage] = useState(0);
  const pingEnvoye = useRef(0);

  useEffect(() => {
    let ws;
    let fermeVolontaire = false;
    let relance;
    let minuteurPing;

    const ouvrir = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/api/ws`);
      ws.onopen = () => {
        setConnecte(true);
        const ping = () => {
          pingEnvoye.current = Date.now();
          if (ws.readyState === WebSocket.OPEN) ws.send("ping");
        };
        ping();
        minuteurPing = setInterval(ping, 30000);
      };
      ws.onmessage = (ev) => {
        const m = JSON.parse(ev.data);
        if (m.type === "etat") setEtat(m.etat);
        if (m.type === "pong") {
          const retour = Date.now();
          const milieu = (pingEnvoye.current + retour) / 2;
          setDecalage(m.heure_serveur - milieu);
        }
      };
      ws.onclose = () => {
        setConnecte(false);
        clearInterval(minuteurPing);
        if (!fermeVolontaire) relance = setTimeout(ouvrir, 1500);
      };
    };
    ouvrir();
    return () => {
      fermeVolontaire = true;
      clearTimeout(relance);
      clearInterval(minuteurPing);
      ws?.close();
    };
  }, []);

  return { etat, connecte, decalage };
}

const CLE_CODE = "arc-replay-code";

function lireMemoire() {
  try {
    return localStorage.getItem(CLE_CODE);
  } catch {
    return null;
  }
}

/** Code de la télécommande : ?code=… dans l'adresse (QR code), sinon mémorisé sur l'appareil. */
export function codeTelecommande() {
  const code = codeDepuisAdresse(location.search, lireMemoire());
  if (code) memoriserCode(code);
  return code;
}

export function memoriserCode(code) {
  try {
    localStorage.setItem(CLE_CODE, code);
  } catch {
    // navigation privée : le code sera redemandé
  }
}

async function envoyer(url, corps) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Arc-Code": codeTelecommande() },
    body: corps === undefined ? undefined : JSON.stringify(corps),
  });
  const reponse = await r.json().catch(() => ({}));
  if (!r.ok) {
    const erreur = new Error(reponse.detail || `Erreur ${r.status}`);
    erreur.codeRequis = r.status === 403;
    throw erreur;
  }
  return reponse;
}

export const commande = (action, params = {}) => envoyer("/api/commande", { action, ...params });
export const recharger = () => envoyer("/api/recharger");
