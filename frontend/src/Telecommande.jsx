import { useState } from "react";
import { commande, recharger, useEtat } from "./api";

const VITESSES = [1, 0.5, 0.25];

function Section({ titre, children }) {
  return (
    <section className="section">
      <h2>{titre}</h2>
      {children}
    </section>
  );
}

export default function Telecommande({ integree = false }) {
  const { etat, connecte } = useEtat();
  const [erreur, setErreur] = useState(null);
  const [voleeOuverte, setVoleeOuverte] = useState(null);
  const [delaiLocal, setDelaiLocal] = useState(null); // valeur pendant le glissement

  const agir = async (action, params) => {
    setErreur(null);
    try {
      await commande(action, params);
    } catch (e) {
      setErreur(e.message);
    }
  };

  if (!etat) return <div className="telecommande telecommande--vide">Connexion au serveur…</div>;

  const rejeu = etat.rejeu;
  const derniere = etat.fleches.at(-1);
  const camerasParId = Object.fromEntries(etat.cameras.map((c) => [c.id, c]));
  const { ordre, masquees, focus } = etat.disposition;
  const volees = [...new Set(etat.fleches.map((f) => f.volee))].reverse();
  const voleeAffichee = voleeOuverte ?? volees[0];

  const deplacer = (id, sens) => {
    const nouvel = [...ordre];
    const i = nouvel.indexOf(id);
    const j = i + sens;
    if (j < 0 || j >= nouvel.length) return;
    [nouvel[i], nouvel[j]] = [nouvel[j], nouvel[i]];
    agir("disposition", { ordre: nouvel });
  };
  const basculerMasque = (id) =>
    agir("disposition", {
      masquees: masquees.includes(id) ? masquees.filter((m) => m !== id) : [...masquees, id],
    });

  const statutFleche = (f) =>
    f.statut === "pret" || f.statut === "partiel" ? null : f.statut === "en_cours" ? "…" : "!";

  return (
    <div className={`telecommande ${integree ? "telecommande--integree" : ""}`}>
      {!integree && (
        <header className="entete">
          <span className={`point ${connecte ? "point--ok" : ""}`} />
          <h1>Arc Replay</h1>
          <span className="entete__seance">
            Volée {etat.volee} · Flèche {etat.fleche}
          </span>
        </header>
      )}

      {erreur && (
        <div className="alerte" onClick={() => setErreur(null)}>
          {erreur}
        </div>
      )}
      {etat.erreurs_cameras?.length > 0 && (
        <div className="alerte alerte--douce">
          {etat.erreurs_cameras.map((e) => (
            <div key={e}>{e}</div>
          ))}
        </div>
      )}

      <Section titre="Rejeu">
        {!rejeu ? (
          <button
            className="bouton bouton--principal bouton--large"
            disabled={!derniere || !Object.keys(derniere.clips).length}
            onClick={() => agir("rejeu", { fleche_id: "derniere" })}
          >
            {!derniere
              ? "Aucune flèche pour l'instant"
              : derniere.statut === "en_cours"
                ? "Préparation du clip…"
                : `Rejouer la dernière flèche (${derniere.id.replace("_", " ")})`}
          </button>
        ) : (
          <>
            <div className="rangee">
              <button className="bouton" onClick={() => agir("rejeu_controle", { lecture: !rejeu.lecture })}>
                {rejeu.lecture ? "Pause" : "Lecture"}
              </button>
              <button className="bouton" onClick={() => agir("rejeu_controle", { redemarrer: true })}>
                Recommencer
              </button>
              <button className="bouton bouton--principal" onClick={() => agir("rejeu_fermer")}>
                Retour au direct
              </button>
            </div>
            <div className="rangee segments">
              {VITESSES.map((v) => (
                <button
                  key={v}
                  className={`bouton ${rejeu.vitesse === v ? "bouton--actif" : ""}`}
                  onClick={() => agir("rejeu_controle", { vitesse: v })}
                >
                  {v === 1 ? "×1" : `×${v}`}
                </button>
              ))}
            </div>
          </>
        )}

        {volees.length > 0 && (
          <>
            <div className="rangee segments segments--defilant">
              {volees.map((v) => (
                <button
                  key={v}
                  className={`bouton bouton--petit ${v === voleeAffichee ? "bouton--actif" : ""}`}
                  onClick={() => setVoleeOuverte(v)}
                >
                  V{v}
                </button>
              ))}
            </div>
            <div className="fleches">
              {etat.fleches
                .filter((f) => f.volee === voleeAffichee)
                .map((f) => (
                  <button
                    key={f.id}
                    className={`fleche ${rejeu?.fleche_id === f.id ? "fleche--active" : ""}`}
                    disabled={!Object.keys(f.clips).length}
                    onClick={() => agir("rejeu", { fleche_id: f.id })}
                  >
                    <span className="fleche__num">F{f.numero}</span>
                    <span className="fleche__score">
                      {f.impact ? (f.impact.x ? "X" : f.impact.score) : "–"}
                    </span>
                    {statutFleche(f) && <span className="fleche__statut">{statutFleche(f)}</span>}
                  </button>
                ))}
            </div>
          </>
        )}
      </Section>

      <Section titre="Séance">
        <div className="rangee">
          <button className="bouton" onClick={() => agir("marquer")}>
            Marquer un tir
          </button>
          <button className="bouton" onClick={() => agir("nouvelle_volee")} disabled={etat.fleche === 0}>
            Nouvelle volée
          </button>
        </div>
        <button
          className="bouton bouton--discret"
          onClick={() => confirm("Commencer une nouvelle séance ? La séance actuelle reste sur le serveur.") &&
            agir("nouvelle_seance")}
        >
          Nouvelle séance
        </button>
      </Section>

      <Section titre="Affichage">
        <label className="reglage">
          <span>
            Retard : <strong>{delaiLocal ?? etat.delai_s} s</strong>
          </span>
          <input
            type="range"
            min="3"
            max="30"
            step="1"
            value={delaiLocal ?? etat.delai_s}
            onChange={(e) => {
              setDelaiLocal(Number(e.target.value));
              agir("delai", { valeur: Number(e.target.value) });
            }}
            onPointerUp={() => setDelaiLocal(null)}
            onBlur={() => setDelaiLocal(null)}
          />
        </label>

        <div className="rangee segments">
          {["droitier", "gaucher"].map((l) => (
            <button
              key={l}
              className={`bouton ${etat.lateralite === l ? "bouton--actif" : ""}`}
              onClick={() => agir("lateralite", { valeur: l })}
            >
              {l === "droitier" ? "Droitier" : "Gaucher"}
            </button>
          ))}
        </div>

        <ul className="cameras">
          {ordre.map((id, i) => {
            const c = camerasParId[id];
            if (!c) return null;
            const cachee = masquees.includes(id);
            return (
              <li key={id} className={cachee ? "camera--cachee" : ""}>
                <span className="camera__nom">
                  {c.nom}
                  {c.ralenti && <small> · {c.fps} i/s</small>}
                </span>
                <button className="icone" aria-label="Monter" disabled={i === 0} onClick={() => deplacer(id, -1)}>
                  ↑
                </button>
                <button className="icone" aria-label="Descendre" disabled={i === ordre.length - 1}
                  onClick={() => deplacer(id, 1)}>
                  ↓
                </button>
                <button className={`icone ${focus === id ? "icone--actif" : ""}`} aria-label="Agrandir"
                  disabled={cachee} onClick={() => agir("focus", { camera: focus === id ? null : id })}>
                  ⤢
                </button>
                <button className="icone" aria-label={cachee ? "Afficher" : "Masquer"} onClick={() => basculerMasque(id)}>
                  {cachee ? "○" : "●"}
                </button>
              </li>
            );
          })}
        </ul>

        <label className="interrupteur">
          <input type="checkbox" checked={etat.afficher_qr}
            onChange={(e) => agir("qr", { valeur: e.target.checked })} />
          Afficher le QR code sur l'écran
        </label>
      </Section>

      <Section titre="Clé USB">
        {etat.usb.presente ? (
          <>
            <p className="info">Clé détectée · {etat.usb.libre_go} Go libres</p>
            <div className="rangee">
              <button className="bouton bouton--principal" disabled={etat.usb.export.etat === "en_cours"}
                onClick={() => agir("export_usb", { portee: "seance" })}>
                Exporter la séance
              </button>
              <button className="bouton" disabled={etat.usb.export.etat === "en_cours"}
                onClick={() => agir("export_usb", { portee: "tout" })}>
                Tout exporter
              </button>
            </div>
          </>
        ) : (
          <p className="info">Branchez une clé USB sur le serveur pour exporter les clips.</p>
        )}
        {etat.usb.export.etat === "en_cours" && (
          <progress max="100" value={etat.usb.export.progression} />
        )}
        {etat.usb.export.message && (
          <p className={`info ${etat.usb.export.etat === "erreur" ? "info--erreur" : ""}`}>
            {etat.usb.export.message}
          </p>
        )}
      </Section>

      <Section titre="Configuration">
        <button
          className="bouton bouton--discret"
          onClick={async () => {
            setErreur(null);
            try {
              await recharger();
            } catch (e) {
              setErreur(e.message);
            }
          }}
        >
          Recharger la configuration des caméras
        </button>
      </Section>
    </div>
  );
}
