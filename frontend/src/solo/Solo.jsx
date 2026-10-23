import { useEffect, useMemo, useRef, useState } from "react";
import { CLIP, clipEnVideo, Moteur, QUALITES, remettreFichier } from "./moteur";
import { annulerDerniere, avecImages, nouvelleVolee, seanceVide, tirer } from "./seance";

const CLE_REGLAGES = "arc-replay-solo";
const DEFAUT = { delai_s: 10, qualite: "standard", camera: "user", micro: true, seuil_db: -20, miroir: false };
const VITESSES = [1, 0.5, 0.25];
const DECALAGE_MANUEL_MS = 1000; // « Marquer » : le tir a eu lieu ~1 s avant l'appui

function lireReglages() {
  try {
    return { ...DEFAUT, ...JSON.parse(localStorage.getItem(CLE_REGLAGES) || "{}") };
  } catch {
    return { ...DEFAUT };
  }
}

function ecrireReglages(r) {
  try {
    localStorage.setItem(CLE_REGLAGES, JSON.stringify(r));
  } catch {
    // navigation privée : réglages non mémorisés
  }
}

const nomFleche = (f) => `V${f.volee} F${f.numero}`;

/** Messages d'erreur caméra compréhensibles. */
function expliquer(e) {
  if (!window.isSecureContext) {
    return "Le navigateur n'autorise la caméra que sur une page sécurisée (https). Ouvrez la version en ligne du mode solo, ou lancez-la en local sur ce PC.";
  }
  if (e?.name === "NotAllowedError") return "Accès à la caméra refusé. Autorisez-le dans les réglages du navigateur, puis réessayez.";
  if (e?.name === "NotFoundError" || e?.name === "OverconstrainedError") return "Aucune caméra trouvée avec ce choix. Essayez l'autre caméra.";
  return `Impossible de démarrer la caméra : ${e?.message || e}`;
}

export default function Solo() {
  const [reglages, setReglagesBruts] = useState(lireReglages);
  const [phase, setPhase] = useState("accueil"); // accueil | demarrage | marche
  const [erreur, setErreur] = useState(null);
  const [seance, setSeance] = useState(seanceVide);
  const [niveau, setNiveau] = useState(-120);
  const [microDispo, setMicroDispo] = useState(false);
  const [panneau, setPanneau] = useState(false);
  const [rejeu, setRejeu] = useState(null); // { ids: [a] ou [a, b], superposer, vitesse, pause }
  const [choixComparaison, setChoixComparaison] = useState(null); // null | [] | [id]
  const [cameras, setCameras] = useState([]);
  const [export_, setExport] = useState(null); // { progression } | { message }
  const [, setTic] = useState(0);

  const seanceRef = useRef(seance);
  seanceRef.current = seance;
  const reglagesRef = useRef(reglages);
  reglagesRef.current = reglages;

  const setReglages = (modif) =>
    setReglagesBruts((r) => {
      const n = { ...r, ...modif };
      ecrireReglages(n);
      return n;
    });

  // --- moteur ----------------------------------------------------------------------

  const moteur = useMemo(() => new Moteur(), []);
  const canvasA = useRef(null);
  const canvasB = useRef(null);

  const lacher = (t) => {
    const r = tirer(seanceRef.current, t);
    if (!r) return;
    seanceRef.current = r.seance;
    setSeance(r.seance);
    const { id } = r.fleche;
    // Le clip est découpé dans la mémoire d'images une fois le suivi filmé
    const attente = t + CLIP.apres_s * 1000 + 300 - performance.now();
    setTimeout(() => {
      const images = moteur.tampon.extraire(t - CLIP.avant_s * 1000, t + CLIP.apres_s * 1000);
      setSeance((s) => avecImages(s, id, images));
    }, Math.max(0, attente));
  };

  moteur.onLacher = lacher;
  moteur.onNiveau = setNiveau;
  moteur.delai_s = reglages.delai_s;
  moteur.detecteur.seuil_db = reglages.seuil_db;
  moteur.microActif = reglages.micro;

  const demarrer = async (modif = {}) => {
    const r = { ...reglagesRef.current, ...modif };
    setErreur(null);
    setPhase("demarrage");
    try {
      const { micro } = await moteur.demarrer(r);
      setMicroDispo(micro);
      setPhase("marche");
      navigator.mediaDevices.enumerateDevices?.().then((d) =>
        setCameras(d.filter((x) => x.kind === "videoinput" && x.deviceId)));
    } catch (e) {
      setErreur(expliquer(e));
      setPhase("accueil");
    }
  };

  useEffect(() => () => moteur.arreter(), [moteur]);

  // Écran toujours allumé pendant la séance
  useEffect(() => {
    if (phase !== "marche" || !navigator.wakeLock) return;
    let verrou = null;
    const prendre = () => navigator.wakeLock.request("screen").then((v) => (verrou = v)).catch(() => {});
    const visible = () => document.visibilityState === "visible" && prendre();
    prendre();
    document.addEventListener("visibilitychange", visible);
    return () => {
      document.removeEventListener("visibilitychange", visible);
      verrou?.release().catch(() => {});
    };
  }, [phase]);

  // Rafraîchit l'affichage des images/s et de la mémoire
  useEffect(() => {
    if (phase !== "marche") return;
    const m = setInterval(() => setTic((x) => x + 1), 1000);
    return () => clearInterval(m);
  }, [phase]);

  // --- rejeu ----------------------------------------------------------------------

  const trouver = (id) => seance.fleches.find((f) => f.id === id);
  const flechesRejeu = rejeu ? rejeu.ids.map(trouver) : [];
  const rejeuValide = rejeu && flechesRejeu.every((f) => f?.images?.length);

  // Dit au moteur quoi dessiner sur quel canvas
  useEffect(() => {
    if (phase !== "marche") return;
    if (!rejeuValide) {
      moteur.arreterRejeu();
      moteur.afficher(canvasA.current ? [{ canvas: canvasA.current, couches: [{}] }] : []);
      return;
    }
    const [a, b] = flechesRejeu;
    if (!b) {
      moteur.afficher([{ canvas: canvasA.current, couches: [{ images: a.images }] }]);
    } else if (rejeu.superposer) {
      moteur.afficher([{ canvas: canvasA.current, couches: [{ images: a.images }, { images: b.images }] }]);
    } else {
      moteur.afficher([
        { canvas: canvasA.current, couches: [{ images: a.images }] },
        { canvas: canvasB.current, couches: [{ images: b.images }] },
      ]);
    }
  }, [phase, rejeuValide, rejeu?.ids.join(), rejeu?.superposer, moteur]);

  // Une volée qui change fait disparaître ses flèches : on ferme leur rejeu
  useEffect(() => {
    if (rejeu && flechesRejeu.some((f) => !f)) setRejeu(null);
  }, [seance]);

  const rejouer = (ids) => {
    const vitesse = rejeu?.vitesse ?? 1;
    setRejeu({ ids, superposer: rejeu?.superposer ?? false, vitesse, pause: false });
    moteur.lancerRejeu(vitesse);
    setPanneau(false);
  };

  const toucherFleche = (f) => {
    if (!f.images?.length) return;
    if (choixComparaison) {
      if (!choixComparaison.length) setChoixComparaison([f.id]);
      else if (choixComparaison[0] !== f.id) {
        rejouer([choixComparaison[0], f.id]);
        setChoixComparaison(null);
      }
      return;
    }
    rejouer([f.id]);
  };

  const reglerRejeu = (modif) => {
    moteur.reglerRejeu(modif);
    setRejeu((r) => ({ ...r, ...(modif.vitesse ? { vitesse: modif.vitesse } : {}),
      ...(modif.pause !== undefined ? { pause: modif.pause } : {}),
      ...(modif.recommencer ? { pause: false } : {}) }));
  };

  const enregistrer = async () => {
    const f = flechesRejeu[0];
    if (!f?.images) return;
    setExport({ progression: 0 });
    try {
      const fichier = await clipEnVideo(f.images, (p) => setExport({ progression: p }));
      const extension = fichier.name.split(".").pop();
      const date = new Date().toISOString().slice(0, 16).replace("T", "_").replace(":", "h");
      await remettreFichier(fichier, `arc-replay_${date}_${f.id}.${extension}`);
      setExport(null);
    } catch (e) {
      setExport({ message: e.message });
    }
  };

  // --- rendu ------------------------------------------------------------------------

  if (phase !== "marche") {
    return (
      <div className="solo-accueil">
        <h1>Arc Replay · mode solo</h1>
        <p>
          Cette tablette ou ce PC filme l'archer avec sa propre caméra et lui montre son geste avec quelques
          secondes de retard. Sans serveur ni Wi-Fi : tout reste sur l'appareil, et seule la volée en cours
          est gardée pour le rejeu.
        </p>
        {!window.isSecureContext && <p className="info info--erreur">{expliquer()}</p>}
        <div className="solo-choix">
          <span>Caméra</span>
          <div className="rangee segments">
            <button className={`bouton ${reglages.camera === "user" ? "bouton--actif" : ""}`}
              onClick={() => setReglages({ camera: "user" })}>Avant (côté écran)</button>
            <button className={`bouton ${reglages.camera === "environment" ? "bouton--actif" : ""}`}
              onClick={() => setReglages({ camera: "environment" })}>Arrière</button>
          </div>
        </div>
        <div className="solo-choix">
          <span>Qualité</span>
          <div className="rangee segments">
            {Object.entries(QUALITES).map(([cle, q]) => (
              <button key={cle} className={`bouton bouton--petit ${reglages.qualite === cle ? "bouton--actif" : ""}`}
                onClick={() => setReglages({ qualite: cle })}>{q.libelle}</button>
            ))}
          </div>
        </div>
        <label className="interrupteur">
          <input type="checkbox" checked={reglages.micro} onChange={(e) => setReglages({ micro: e.target.checked })} />
          Détecter les tirs au micro (sinon, bouton « Marquer »)
        </label>
        {erreur && <p className="info info--erreur">{erreur}</p>}
        <button className="bouton bouton--principal bouton--large" disabled={phase === "demarrage"}
          onClick={() => demarrer()}>
          {phase === "demarrage" ? "Démarrage…" : "Démarrer"}
        </button>
        <p className="info">
          Posez l'appareil du côté vers lequel l'archer est tourné, hors de la trajectoire des flèches.
          Pour l'installer comme une application : menu du navigateur, « Ajouter à l'écran d'accueil ».
        </p>
      </div>
    );
  }

  const derniere = seance.fleches.at(-1);
  const memoireMo = Math.round((moteur.tampon.octets
    + seance.fleches.reduce((s, f) => s + (f.images ?? []).reduce((x, im) => x + im.octets, 0), 0)) / 1e6);
  const enComparaison = flechesRejeu.length === 2;
  const deuxCanvas = rejeuValide && enComparaison && !rejeu.superposer;

  return (
    <div className={`solo ${reglages.miroir ? "solo--miroir" : ""}`}>
      <div className={`solo__ecrans ${deuxCanvas ? "solo__ecrans--deux" : ""}`}>
        <canvas ref={canvasA} />
        {deuxCanvas && <canvas ref={canvasB} />}
      </div>

      <div className="hud">
        {microDispo && reglages.micro && (
          <span className={`point ${niveau >= reglages.seuil_db ? "point--ok" : ""}`} title="Micro" />
        )}
        {rejeuValide ? (
          <span className="pastille pastille--forte">
            {enComparaison
              ? `${nomFleche(flechesRejeu[0])} / ${nomFleche(flechesRejeu[1])}${rejeu.superposer ? " (superposées)" : ""}`
              : `Rejeu ${nomFleche(flechesRejeu[0])}`}
            {rejeu.vitesse !== 1 ? ` · ×${rejeu.vitesse}` : ""}
          </span>
        ) : (
          <span className="pastille pastille--forte">−{reglages.delai_s} s</span>
        )}
        <span className="hud__compteur">Volée {seance.volee} · Flèche {seance.fleche}</span>
      </div>

      <div className="solo__barre">
        <div className="solo__fleches">
          {seance.fleches.map((f) => (
            <button key={f.id}
              className={`fleche ${rejeu?.ids.includes(f.id) || choixComparaison?.includes(f.id) ? "fleche--active" : ""}`}
              disabled={!f.images?.length} onClick={() => toucherFleche(f)}>
              <span className="fleche__num">F{f.numero}</span>
              {!f.images && <span className="fleche__statut">…</span>}
            </button>
          ))}
        </div>

        {rejeuValide ? (
          <div className="rangee">
            <button className="bouton" onClick={() => reglerRejeu({ pause: !rejeu.pause })}>
              {rejeu.pause ? "Lecture" : "Pause"}
            </button>
            {VITESSES.map((v) => (
              <button key={v} className={`bouton ${rejeu.vitesse === v ? "bouton--actif" : ""}`}
                onClick={() => reglerRejeu({ vitesse: v })}>×{v}</button>
            ))}
            <button className="bouton" onClick={() => reglerRejeu({ recommencer: true })}>Recommencer</button>
            {enComparaison ? (
              <button className="bouton" onClick={() => setRejeu((r) => ({ ...r, superposer: !r.superposer }))}>
                {rejeu.superposer ? "Côte à côte" : "Superposer"}
              </button>
            ) : (
              <button className="bouton" disabled={!!export_ && "progression" in export_}
                onClick={enregistrer}>
                {export_ && "progression" in export_ ? `Vidéo… ${Math.round(export_.progression * 100)} %` : "Enregistrer la vidéo"}
              </button>
            )}
            <button className="bouton bouton--principal" onClick={() => setRejeu(null)}>Retour au direct</button>
          </div>
        ) : (
          <div className="rangee">
            <button className="bouton bouton--principal" onClick={() => lacher(performance.now() - DECALAGE_MANUEL_MS)}>
              Marquer un tir
            </button>
            <button className="bouton" disabled={!derniere?.images?.length} onClick={() => rejouer([derniere.id])}>
              Rejouer
            </button>
            <button className={`bouton ${choixComparaison ? "bouton--actif" : ""}`}
              disabled={seance.fleches.filter((f) => f.images?.length).length < 2}
              onClick={() => setChoixComparaison(choixComparaison ? null : [])}>
              {choixComparaison
                ? choixComparaison.length ? "Seconde flèche…" : "Première flèche…"
                : "Comparer"}
            </button>
            <button className="bouton" onClick={() => setPanneau(!panneau)}>Réglages</button>
          </div>
        )}
        {export_?.message && <p className="info info--erreur" onClick={() => setExport(null)}>{export_.message}</p>}
      </div>

      {panneau && (
        <div className="tiroir solo__panneau">
          <section className="section">
            <h2>Affichage</h2>
            <label className="reglage">
              <span>Retard : <strong>{reglages.delai_s} s</strong></span>
              <input type="range" min="3" max="30" step="1" value={reglages.delai_s}
                onChange={(e) => setReglages({ delai_s: Number(e.target.value) })} />
            </label>
            <label className="interrupteur">
              <input type="checkbox" checked={reglages.miroir} onChange={(e) => setReglages({ miroir: e.target.checked })} />
              Image en miroir
            </label>
          </section>

          <section className="section">
            <h2>Séance</h2>
            <div className="rangee">
              <button className="bouton" disabled={seance.fleche === 0}
                onClick={() => setSeance((s) => nouvelleVolee(s))}>Nouvelle volée</button>
              <button className="bouton" disabled={!derniere}
                onClick={() => confirm(`Annuler la flèche ${nomFleche(derniere)} ?`) && setSeance((s) => annulerDerniere(s))}>
                Annuler la dernière flèche
              </button>
            </div>
          </section>

          <section className="section">
            <h2>Micro</h2>
            {microDispo ? (
              <>
                <label className="interrupteur">
                  <input type="checkbox" checked={reglages.micro}
                      onChange={(e) => setReglages({ micro: e.target.checked })} />
                  Détecter les tirs au micro
                </label>
                <label className="reglage">
                  <span>Seuil : <strong>{reglages.seuil_db} dB</strong> · niveau actuel {Math.round(niveau)} dB</span>
                  <input type="range" min="-50" max="-3" step="1" value={reglages.seuil_db}
                    onChange={(e) => setReglages({ seuil_db: Number(e.target.value) })} />
                  <meter min="-60" max="0" value={Math.max(-60, niveau)} />
                </label>
                <p className="info">Réglez le seuil juste au-dessus du bruit ambiant : le claquement de corde doit le dépasser, pas les voix.</p>
              </>
            ) : (
              <p className="info">Micro indisponible : utilisez « Marquer un tir ».</p>
            )}
          </section>

          <section className="section">
            <h2>Caméra</h2>
            <div className="rangee segments">
              {[["user", "Avant"], ["environment", "Arrière"]].map(([cle, nom]) => (
                <button key={cle} className={`bouton ${reglages.camera === cle ? "bouton--actif" : ""}`}
                  onClick={() => { setReglages({ camera: cle }); demarrer({ camera: cle }); }}>{nom}</button>
              ))}
            </div>
            {cameras.length > 1 && (
              <select className="champ" value={cameras.some((c) => c.deviceId === reglages.camera) ? reglages.camera : ""}
                onChange={(e) => { setReglages({ camera: e.target.value }); demarrer({ camera: e.target.value }); }}>
                <option value="" disabled>Choisir une caméra…</option>
                {cameras.map((c, i) => <option key={c.deviceId} value={c.deviceId}>{c.label || `Caméra ${i + 1}`}</option>)}
              </select>
            )}
            <div className="rangee segments">
              {Object.entries(QUALITES).map(([cle, q]) => (
                <button key={cle} className={`bouton bouton--petit ${reglages.qualite === cle ? "bouton--actif" : ""}`}
                  onClick={() => { setReglages({ qualite: cle }); demarrer({ qualite: cle }); }}>{q.libelle}</button>
              ))}
            </div>
            <p className="info">{moteur.ips} images/s · {memoireMo} Mo en mémoire</p>
          </section>

          <button className="bouton bouton--principal bouton--large" onClick={() => setPanneau(false)}>Fermer</button>
        </div>
      )}
    </div>
  );
}
