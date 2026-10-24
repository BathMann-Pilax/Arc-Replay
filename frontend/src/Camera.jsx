import { useRef, useState } from "react";
import { DetecteurLacher, niveauDbfs } from "./solo/son";

const FORMAT_PAYSAGE = { width: { ideal: 1280 }, height: { ideal: 720 }, aspectRatio: { ideal: 16 / 9 } };

/**
 * Demande la caméra au format paysage (évite l'image verticale rognée sur l'écran). Si
 * l'appareil refuse ces contraintes (OverconstrainedError), on les enlève une par une :
 * d'abord le format, puis « avant/arrière » lui-même (webcams d'ordinateur, qui n'ont pas
 * de face avant/arrière et que Safari refuse alors même en préférence « ideal »).
 */
async function fluxCamera(deviceId, audio) {
  const choix = deviceId ? { deviceId: { exact: deviceId } } : { facingMode: { ideal: "environment" } };
  const essais = [{ ...choix, ...FORMAT_PAYSAGE }, choix, deviceId ? choix : true];
  let derniere;
  for (const video of essais) {
    try {
      return await navigator.mediaDevices.getUserMedia({ video, audio });
    } catch (e) {
      if (e.name !== "OverconstrainedError") throw e;
      derniere = e;
    }
  }
  throw derniere;
}

/** Publie la vidéo vers MediaMTX en WHIP (WebRTC-HTTP Ingestion), sans ffmpeg. */
async function publierWhip(stream, id) {
  const pc = new RTCPeerConnection();
  stream.getVideoTracks().forEach((piste) => {
    const emetteur = pc.addTransceiver(piste, { direction: "sendonly" });
    // MediaMTX ne sait remuxer le direct (HLS) qu'en H.264 : sans ça, un navigateur qui
    // choisit VP8 par défaut (Chrome/Safari sur Mac, pas sur mobile) publie un flux que
    // l'écran ne pourra jamais lire (« muxer is waiting to be created » indéfiniment).
    const h264 = RTCRtpSender.getCapabilities?.("video")?.codecs.filter((c) => /H264/i.test(c.mimeType)) ?? [];
    // Priorité au profil le plus largement supporté (42e01f, « constrained baseline ») :
    // le profil préféré du navigateur n'est pas forcément celui que MediaMTX accepte.
    const prioritaires = [
      ...h264.filter((c) => c.sdpFmtpLine?.includes("42e01f")),
      ...h264.filter((c) => !c.sdpFmtpLine?.includes("42e01f")),
    ];
    if (prioritaires.length) emetteur.setCodecPreferences(prioritaires);
  });

  const offre = await pc.createOffer();
  await pc.setLocalDescription(offre);
  await new Promise((resoudre) => {
    if (pc.iceGatheringState === "complete") return resoudre();
    const verifier = () => {
      if (pc.iceGatheringState === "complete") {
        pc.removeEventListener("icegatheringstatechange", verifier);
        resoudre();
      }
    };
    pc.addEventListener("icegatheringstatechange", verifier);
  });

  const reponse = await fetch(`/webrtc/${id}/whip`, {
    method: "POST",
    headers: { "Content-Type": "application/sdp" },
    body: pc.localDescription.sdp,
  });
  if (!reponse.ok) {
    pc.close();
    throw new Error("le serveur vidéo a refusé la publication");
  }
  const sdpReponse = await reponse.text();
  await pc.setRemoteDescription({ type: "answer", sdp: sdpReponse });
  const session = reponse.headers.get("Location");
  return { pc, sessionUrl: session ? new URL(session, reponse.url).toString() : null };
}

export default function Camera() {
  const [nom, setNom] = useState("");
  const [camActif, setCamActif] = useState(true);
  const [micActif, setMicActif] = useState(false);
  const [cameraId, setCameraId] = useState(""); // "" = caméra arrière par défaut
  const [camerasDisponibles, setCamerasDisponibles] = useState([]);
  const [seuil, setSeuil] = useState(-20);
  const [niveau, setNiveau] = useState(-120);
  const [etat, setEtat] = useState("arret"); // arret | demarrage | direct | erreur
  const [erreur, setErreur] = useState(null);
  const videoRef = useRef(null);
  const refCam = useRef(null); // { id, pc, sessionUrl, stream, audio: { contexte, minuteur } }
  const seuilRef = useRef(seuil);
  seuilRef.current = seuil;

  const ecouterMicro = (stream) => {
    const Contexte = window.AudioContext || window.webkitAudioContext;
    const contexte = new Contexte();
    contexte.resume().catch(() => {});
    const source = contexte.createMediaStreamSource(stream);
    const analyse = contexte.createAnalyser();
    analyse.fftSize = 2048;
    source.connect(analyse);
    const bloc = new Float32Array(analyse.fftSize);
    const detecteur = new DetecteurLacher(seuilRef.current, 2000);
    let maxi = -120;
    let dernierEnvoi = 0;
    const minuteur = setInterval(() => {
      analyse.getFloatTimeDomainData(bloc);
      const n = niveauDbfs(bloc);
      const t = performance.now();
      maxi = Math.max(maxi, n);
      if (t - dernierEnvoi > 150) {
        setNiveau(maxi);
        maxi = -120;
        dernierEnvoi = t;
      }
      detecteur.seuil_db = seuilRef.current;
      if (detecteur.bloc(n, t)) {
        fetch("/api/lacher", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ source: "audio" }),
        }).catch(() => {});
      }
    }, 20);
    return { contexte, minuteur };
  };

  const arreterFlux = () => {
    const c = refCam.current;
    refCam.current = null;
    if (c?.audio) {
      clearInterval(c.audio.minuteur);
      c.audio.contexte.close().catch(() => {});
    }
    c?.pc?.close();
    c?.stream?.getTracks().forEach((piste) => piste.stop());
    if (c?.sessionUrl) fetch(c.sessionUrl, { method: "DELETE" }).catch(() => {});
    if (c?.id) fetch(`/api/cameras/telephone/${c.id}`, { method: "DELETE" }).catch(() => {});
  };

  const demarrer = async (deviceId = cameraId) => {
    if (!camActif && !micActif) {
      setErreur("choisissez au moins la caméra ou le micro");
      return;
    }
    setErreur(null);
    setEtat("demarrage");
    let stream;
    let id = null;
    try {
      stream = camActif
        ? await fluxCamera(deviceId, micActif)
        : await navigator.mediaDevices.getUserMedia({ video: false, audio: micActif });
      if (camActif && videoRef.current) videoRef.current.srcObject = stream;

      let pc = null;
      let sessionUrl = null;
      if (camActif) {
        const reponse = await fetch("/api/cameras/telephone", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ nom: nom.trim() || "Téléphone" }),
        });
        if (!reponse.ok) throw new Error("le serveur a refusé la caméra");
        ({ id } = await reponse.json());
        ({ pc, sessionUrl } = await publierWhip(stream, id));
        // Labels disponibles seulement après l'autorisation : on liste maintenant.
        navigator.mediaDevices.enumerateDevices?.().then((liste) =>
          setCamerasDisponibles(liste.filter((a) => a.kind === "videoinput" && a.deviceId)));
      }

      const audio = micActif ? ecouterMicro(stream) : null;
      refCam.current = { id, pc, sessionUrl, stream, audio };
      setEtat("direct");
    } catch (e) {
      stream?.getTracks().forEach((piste) => piste.stop());
      // La caméra a été enregistrée côté serveur mais la publication a échoué ensuite :
      // on la retire pour ne pas laisser une vue fantôme dans la mosaïque.
      if (id) fetch(`/api/cameras/telephone/${id}`, { method: "DELETE" }).catch(() => {});
      const appareils = await navigator.mediaDevices.enumerateDevices().catch(() => []);
      console.error("Arc Replay /camera :", e, "contrainte :", e.constraint, "appareils :", appareils);
      setErreur(
        `${e.name || "erreur"}${e.constraint ? ` (contrainte : ${e.constraint})` : ""} : ` +
        `${e.message || "impossible de démarrer"} — ${appareils.filter((a) => a.kind === "videoinput").length} caméra(s) détectée(s)`
      );
      setEtat("erreur");
    }
  };

  const changerCamera = async (deviceId) => {
    setCameraId(deviceId);
    if (etat === "direct") {
      arreterFlux();
      await demarrer(deviceId);
    }
  };

  const arreter = () => {
    arreterFlux();
    setEtat("arret");
    setNiveau(-120);
  };

  if (!window.isSecureContext) {
    return (
      <div className="camera camera--erreur">
        <p>
          Cette page doit être ouverte en <strong>https</strong> pour accéder à la caméra ou au micro.
          Scannez le QR code affiché dans la télécommande (section « Configuration »).
        </p>
      </div>
    );
  }

  return (
    <div className="camera">
      <h1>Caméra / micro</h1>
      {etat !== "direct" && (
        <>
          <label className="interrupteur">
            <input type="checkbox" checked={camActif} onChange={(e) => setCamActif(e.target.checked)} />
            Caméra (ajoutée à la mosaïque de l'écran)
          </label>
          <label className="interrupteur">
            <input type="checkbox" checked={micActif} onChange={(e) => setMicActif(e.target.checked)} />
            Micro : détecter le tir (claquement de corde)
          </label>
          {camActif && (
            <input
              className="champ"
              placeholder="Nom de la caméra (ex : tribune)"
              value={nom}
              onChange={(e) => setNom(e.target.value)}
            />
          )}
          <button
            className="bouton bouton--principal bouton--large"
            disabled={etat === "demarrage"}
            onClick={() => demarrer()}
          >
            {etat === "demarrage" ? "Démarrage…" : "Démarrer"}
          </button>
        </>
      )}
      {erreur && <div className="alerte">{erreur}</div>}
      {camActif && <video ref={videoRef} autoPlay playsInline muted className="camera__apercu" />}
      {etat === "direct" && (
        <>
          {refCam.current?.id && <p className="info">Caméra en direct sur l'écran du serveur.</p>}
          {camActif && camerasDisponibles.length > 1 && (
            <label className="reglage">
              <span>Caméra utilisée</span>
              <select className="champ" value={cameraId} onChange={(e) => changerCamera(e.target.value)}>
                <option value="">Par défaut (arrière)</option>
                {camerasDisponibles.map((c, i) => (
                  <option key={c.deviceId} value={c.deviceId}>{c.label || `Caméra ${i + 1}`}</option>
                ))}
              </select>
            </label>
          )}
          {micActif && (
            <div className="camera__micro">
              <p className="info">
                Micro actif : un lâcher est signalé dès que le niveau dépasse le seuil. Réglez le
                seuil juste au-dessus du niveau au repos (sans tirer).
              </p>
              <meter min="-60" max="0" value={Math.max(niveau, -60)} />
              <label className="reglage">
                <span>Seuil : {seuil} dBFS</span>
                <input
                  type="range"
                  min="-60"
                  max="0"
                  step="1"
                  value={seuil}
                  onChange={(e) => setSeuil(Number(e.target.value))}
                />
              </label>
            </div>
          )}
          <button className="bouton bouton--discret" onClick={arreter}>
            Arrêter
          </button>
        </>
      )}
    </div>
  );
}
