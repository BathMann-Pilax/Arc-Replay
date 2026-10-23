import { useEffect, useRef, useState } from "react";

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

export async function commande(action, params = {}) {
  const r = await fetch("/api/commande", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, ...params }),
  });
  if (!r.ok) {
    const corps = await r.json().catch(() => ({}));
    throw new Error(corps.detail || `Erreur ${r.status}`);
  }
  return r.json();
}

export async function recharger() {
  const r = await fetch("/api/recharger", { method: "POST" });
  const corps = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(corps.detail || `Erreur ${r.status}`);
  return corps;
}

export const urlFichier = (relatif) => `/fichiers/${relatif.split("/").map(encodeURIComponent).join("/")}`;

/** Caméras visibles, dans l'ordre choisi. */
export function camerasVisibles(etat) {
  if (!etat) return [];
  const parId = Object.fromEntries(etat.cameras.map((c) => [c.id, c]));
  return etat.disposition.ordre
    .filter((id) => parId[id] && !etat.disposition.masquees.includes(id))
    .map((id) => parId[id]);
}

export const estMiroir = (camera, etat) => etat?.lateralite === "gaucher" && camera.miroir_gaucher;
