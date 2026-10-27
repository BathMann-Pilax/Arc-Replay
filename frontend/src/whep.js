// Lecture WebRTC d'un chemin MediaMTX par WHEP (sans bibliothèque).
// Le signalement passe par nginx (/webrtc/) ; la vidéo arrive directement sur
// le port ICE de MediaMTX (8189). Réseau local : pas de serveur STUN.

export const adresseWhep = (cheminCamera) => `/webrtc/${encodeURIComponent(cheminCamera)}/whep`;

export const webrtcDisponible = () => typeof window !== "undefined" && "RTCPeerConnection" in window;

/**
 * Stratégie après `echecs` échecs WebRTC consécutifs :
 * deux essais WebRTC rapprochés, puis le HLS au bord du direct, en retentant
 * le WebRTC toutes les 30 s.
 */
export function strategie(echecs, webrtc = true) {
  if (!webrtc) return { mode: "hls", reessayerWebrtcMs: null };
  if (echecs < 2) return { mode: "webrtc", attenteMs: echecs === 0 ? 0 : 2000 };
  return { mode: "hls", reessayerWebrtcMs: 30000 };
}

function attendreCandidats(pc, delaiMs) {
  // Sans STUN, les candidats locaux sont prêts en quelques millisecondes
  return new Promise((ok) => {
    if (pc.iceGatheringState === "complete") return ok();
    const minuteur = setTimeout(ok, delaiMs);
    pc.addEventListener("icegatheringstatechange", () => {
      if (pc.iceGatheringState === "complete") {
        clearTimeout(minuteur);
        ok();
      }
    });
  });
}

/**
 * Ouvre la lecture WebRTC dans `video`. Renvoie une fonction de fermeture.
 * `surEchec` est appelé si la connexion échoue ou se coupe.
 */
export async function lireWhep(video, cheminCamera, { surImage, surEchec } = {}) {
  const pc = new RTCPeerConnection({ iceServers: [] });
  let session = null;
  let fini = false;
  const fermer = () => {
    if (fini) return;
    fini = true;
    pc.close();
    if (session) fetch(session, { method: "DELETE" }).catch(() => {});
  };
  pc.addTransceiver("video", { direction: "recvonly" });
  pc.ontrack = (e) => {
    video.srcObject = e.streams && e.streams[0] ? e.streams[0] : new MediaStream([e.track]);
    video.play().catch(() => {});
  };
  pc.onconnectionstatechange = () => {
    if (!fini && (pc.connectionState === "failed" || pc.connectionState === "disconnected")) {
      fermer();
      surEchec && surEchec(new Error(`WebRTC ${pc.connectionState}`));
    }
  };
  video.addEventListener("playing", () => surImage && surImage(), { once: true });
  try {
    await pc.setLocalDescription(await pc.createOffer());
    await attendreCandidats(pc, 1500);
    const reponse = await fetch(adresseWhep(cheminCamera), {
      method: "POST",
      headers: { "Content-Type": "application/sdp" },
      body: pc.localDescription.sdp,
    });
    if (!reponse.ok) throw new Error(`WHEP ${reponse.status}`);
    session = reponse.headers.get("Location");
    await pc.setRemoteDescription({ type: "answer", sdp: await reponse.text() });
  } catch (e) {
    fermer();
    throw e;
  }
  return fermer;
}
