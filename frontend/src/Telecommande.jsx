import { useState } from "react";
import { commande, memoriserCode, recharger, useEtat } from "./api";
import { BLASONS, camerasCommunes, indexBlason, libelleScore, rejouable, valeurScore } from "./logique";
import EditeurCadrage from "./EditeurCadrage";
import EditeurReperes from "./EditeurReperes";

const VITESSES = [1, 0.5, 0.25];
const SCORES = [["X", 10, true], ["10", 10], ["9", 9], ["8", 8], ["7", 7], ["6", 6],
  ["5", 5], ["4", 4], ["3", 3], ["2", 2], ["1", 1], ["M", 0]];

function Section({ titre, children }) {
  return (
    <section className="section">
      <h2>{titre}</h2>
      {children}
    </section>
  );
}

function DemandeCode({ onValide }) {
  const [code, setCode] = useState("");
  return (
    <form
      className="alerte alerte--douce"
      onSubmit={(e) => {
        e.preventDefault();
        memoriserCode(code.trim());
        onValide();
      }}
    >
      <p>Code de la télécommande (affiché dans le QR code de l'écran) :</p>
      <div className="rangee">
        <input className="champ" value={code} onChange={(e) => setCode(e.target.value)}
          autoFocus inputMode="numeric" aria-label="Code" />
        <button className="bouton bouton--principal" type="submit">Valider</button>
      </div>
    </form>
  );
}

function AjoutCamera({ qrType, agir }) {
  const surEcran = qrType === "camera";
  return (
    <>
      <button
        className={`bouton bouton--discret ${surEcran ? "bouton--actif" : ""}`}
        onClick={() => agir("qr", { valeur: surEcran ? "telecommande" : "camera" })}
      >
        {surEcran ? "Afficher le QR de la télécommande sur l'écran" : "Ajouter une caméra depuis un téléphone"}
      </button>
      {surEcran && (
        <p className="info">
          QR code affiché sur l'écran : à scanner avec le téléphone qui filmera. Même réseau Wi-Fi
          que le serveur. Premier accès : avertissement de sécurité (certificat local) à valider,
          puis autoriser la caméra.
        </p>
      )}
    </>
  );
}

export default function Telecommande({ integree = false }) {
  const { etat, connecte } = useEtat();
  const [erreur, setErreur] = useState(null);
  const [codeDemande, setCodeDemande] = useState(false);
  const [voleeOuverte, setVoleeOuverte] = useState(null);
  const [delaiLocal, setDelaiLocal] = useState(null); // valeur pendant le glissement
  const [selection, setSelection] = useState(null); // flèche choisie pour le score
  const [comparaison, setComparaison] = useState(null); // null, ou [] puis [id A] en cours de choix
  const [editeurReperes, setEditeurReperes] = useState(false);
  const [editeurCadrage, setEditeurCadrage] = useState(false);

  const agir = async (action, params) => {
    setErreur(null);
    try {
      await commande(action, params);
      return true;
    } catch (e) {
      if (e.codeRequis) setCodeDemande(true);
      else setErreur(e.message);
      return false;
    }
  };

  if (!etat) return <div className="telecommande telecommande--vide">Connexion au serveur…</div>;

  const rejeu = etat.rejeu;
  const derniere = etat.fleches.at(-1);
  const camerasParId = Object.fromEntries(etat.cameras.map((c) => [c.id, c]));
  const { ordre, masquees, focus } = etat.disposition;
  const miroir = etat.disposition.miroir || [];
  const volees = [...new Set(etat.fleches.map((f) => f.volee))].reverse();
  const voleeAffichee = voleeOuverte ?? volees[0];
  const trouver = (id) => etat.fleches.find((f) => f.id === id);
  const aNoter = trouver(selection) ?? derniere;
  const flecheA = rejeu?.fleche_id_b ? trouver(rejeu.fleche_id) : null;
  const flecheB = rejeu?.fleche_id_b ? trouver(rejeu.fleche_id_b) : null;
  const groupement = etat.groupements?.volee;
  const groupementSeance = etat.groupements?.seance;
  const espaceBas = etat.disque?.libre_go != null && etat.disque.libre_go < etat.disque.alerte_go;

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
  const basculerMiroir = (id) =>
    agir("disposition", {
      miroir: miroir.includes(id) ? miroir.filter((m) => m !== id) : [...miroir, id],
    });

  const statutFleche = (f) =>
    f.archivee ? null : f.statut === "pret" || f.statut === "partiel" ? null : f.statut === "en_cours" ? "…" : "!";

  const toucherFleche = async (f) => {
    if (comparaison === null) setSelection(f.id);
    if (comparaison !== null) {
      if (!rejouable(f)) return;
      if (comparaison.length === 0) {
        setComparaison([f.id]);
      } else if (comparaison[0] !== f.id) {
        if (await agir("comparer", { fleche_id: comparaison[0], fleche_id_b: f.id, camera: focus })) {
          setComparaison(null);
        }
      }
      return;
    }
    if (rejouable(f)) agir("rejeu", { fleche_id: f.id });
  };

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

      {codeDemande && <DemandeCode onValide={() => setCodeDemande(false)} />}
      {erreur && (
        <div className="alerte" onClick={() => setErreur(null)}>
          {erreur}
        </div>
      )}
      {espaceBas && (
        <div className="alerte">
          Plus que {etat.disque.libre_go} Go libres sur le serveur. Terminez la séance pour le vider.
        </div>
      )}
      {etat.erreurs_cameras?.length > 0 && (
        <div className="alerte alerte--douce">
          {etat.erreurs_cameras.map((e) => (
            <div key={e}>{e}</div>
          ))}
        </div>
      )}

      {/* Grand écran (tablette) : deux colonnes, le tir à gauche, les réglages à droite */}
      <div className="colonnes">
      <div className="colonne">
      <Section titre="Rejeu">
        {!rejeu ? (
          <button
            className="bouton bouton--principal bouton--large"
            disabled={!rejouable(derniere)}
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
            {flecheA && flecheB && (
              <>
                <div className="rangee segments">
                  <button className={`bouton ${!rejeu.superposer ? "bouton--actif" : ""}`}
                    onClick={() => agir("rejeu_controle", { superposer: false })}>
                    Côte à côte
                  </button>
                  <button className={`bouton ${rejeu.superposer ? "bouton--actif" : ""}`}
                    onClick={() => agir("rejeu_controle", { superposer: true })}>
                    Superposées
                  </button>
                </div>
                <div className="rangee segments segments--defilant">
                  {camerasCommunes(etat, flecheA, flecheB).map((c) => (
                    <button key={c.id} className={`bouton bouton--petit ${rejeu.camera === c.id ? "bouton--actif" : ""}`}
                      onClick={() => agir("rejeu_controle", { camera: c.id })}>
                      {c.nom}
                    </button>
                  ))}
                </div>
              </>
            )}
          </>
        )}

        <button
          className={`bouton bouton--discret ${comparaison !== null ? "bouton--actif" : ""}`}
          onClick={() => setComparaison(comparaison === null ? [] : null)}
        >
          {comparaison === null
            ? "Comparer deux flèches"
            : comparaison.length === 0
              ? "Touchez la première flèche… (annuler)"
              : "Touchez la seconde flèche… (annuler)"}
        </button>

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
                    className={[
                      "fleche",
                      rejeu && [rejeu.fleche_id, rejeu.fleche_id_b].includes(f.id) ? "fleche--active" : "",
                      aNoter?.id === f.id ? "fleche--choisie" : "",
                      comparaison?.includes(f.id) ? "fleche--active" : "",
                      f.archivee ? "fleche--archivee" : "",
                    ].join(" ")}
                    onClick={() => toucherFleche(f)}
                  >
                    <span className="fleche__num">F{f.numero}</span>
                    <span className="fleche__score">
                      {libelleScore(f.impact)}
                      {f.impact?.doute && <span className="score__doute" title="Sur la ligne, à confirmer">?</span>}
                    </span>
                    {statutFleche(f) && <span className="fleche__statut">{statutFleche(f)}</span>}
                  </button>
                ))}
            </div>
            {voleeAffichee !== etat.volee && etat.fleches.some((f) => f.volee === voleeAffichee && f.archivee) && (
              <p className="info">
                Volée terminée : ses vidéos {etat.usb.presente ? "sont sur la clé USB" : "ont été effacées du serveur"}.
                Les scores restent.
              </p>
            )}
          </>
        )}
      </Section>

      <Section titre="Score">
        <div className="rangee">
          <select className="champ" aria-label="Blason" value={indexBlason(etat.blason)}
            onChange={(e) => {
              const choisi = BLASONS[Number(e.target.value)];
              if (choisi) agir("blason", { blason: { ...choisi.blason, poulies: !!etat.blason?.poulies } });
            }}>
            {indexBlason(etat.blason) === -1 && <option value={-1}>Blason de la configuration</option>}
            {BLASONS.map((b, i) => <option key={b.nom} value={i}>{b.nom}</option>)}
          </select>
        </div>
        <label className="interrupteur">
          <input type="checkbox" checked={!!etat.blason?.poulies}
            onChange={(e) => agir("blason", { blason: { ...etat.blason, poulies: e.target.checked } })} />
          Arc à poulies (10 réduit)
        </label>

        {aNoter ? (
          <>
            <p className="info">
              Flèche {aNoter.id.replace("_", " ")} : <strong>{libelleScore(aNoter.impact)}</strong>
              {aNoter.impact?.manuel ? " (saisi)" : aNoter.impact ? " (détecté)" : ""}
              {aNoter.impact?.double && " : seconde flèche dans ce spot, comptée M (règle du trispot)"}
            </p>
            {aNoter.impact?.doute && (
              <div className="alerte alerte--douce">
                <p className="info">Sur la ligne : {libelleScore(aNoter.impact)} ou {aNoter.impact.alternative} ?</p>
                <div className="rangee">
                  {[libelleScore(aNoter.impact), aNoter.impact.alternative].map((l) => (
                    <button key={l} className={`bouton bouton--petit score-${l}`}
                      onClick={() => agir("score", { fleche_id: aNoter.id, ...valeurScore(l) })}>
                      {l}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="clavier-score">
              {SCORES.map(([libelle, valeur, x]) => (
                <button key={libelle} className={`bouton bouton--petit score-${libelle}`}
                  onClick={() => agir("score", { fleche_id: aNoter.id, valeur, x: !!x })}>
                  {libelle}
                </button>
              ))}
            </div>
          </>
        ) : (
          <p className="info">Le score se saisit ici quand la cible n'est pas filmée.</p>
        )}
        {(groupement || groupementSeance) && (
          <p className="info">
            {groupement && <>Groupement volée : ⌀ {Math.round(groupement.dispersion_mm * 2)} mm. </>}
            {groupementSeance && <>Séance : ⌀ {Math.round(groupementSeance.dispersion_mm * 2)} mm
              ({groupementSeance.n} impacts).</>}
          </p>
        )}
      </Section>
      </div>

      <div className="colonne">
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
          className="bouton"
          disabled={!derniere || derniere.volee !== etat.volee || etat.fleche === 0}
          onClick={() => confirm(`Annuler la flèche ${derniere.id.replace("_", " ")} (faux lâcher) ?`) &&
            agir("annuler_fleche")}
        >
          Annuler la dernière flèche
        </button>
        <button
          className="bouton bouton--discret"
          disabled={derniere?.statut === "en_cours"}
          onClick={() => confirm(
            etat.usb.presente
              ? "Terminer la séance ? La volée en cours sera enregistrée sur la clé, puis le serveur sera vidé."
              : "Terminer la séance ? Sans clé USB, les vidéos seront effacées.") &&
            agir("nouvelle_seance")}
        >
          Fin de séance
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
                <button className={`icone ${miroir.includes(id) ? "icone--actif" : ""}`}
                  aria-label="Miroir" title="Retourner l'image (miroir)" onClick={() => basculerMiroir(id)}>
                  ⇆
                </button>
                <button className="icone" aria-label={cachee ? "Afficher" : "Masquer"} onClick={() => basculerMasque(id)}>
                  {cachee ? "○" : "●"}
                </button>
              </li>
            );
          })}
        </ul>

        <div className="rangee">
          <button className={`bouton ${etat.grille ? "bouton--actif" : ""}`}
            onClick={() => agir("grille", { valeur: !etat.grille })}>
            Grille
          </button>
          <button className={`bouton ${editeurReperes ? "bouton--actif" : ""}`}
            onClick={() => setEditeurReperes(!editeurReperes)}>
            Lignes de repère
          </button>
        </div>
        {editeurReperes && <EditeurReperes etat={etat} agir={agir} />}
        {etat.cameras.some((c) => c.recadrage) && (
          <button className={`bouton ${editeurCadrage ? "bouton--actif" : ""}`}
            onClick={() => setEditeurCadrage(!editeurCadrage)}>
            Cadrage de la cible
          </button>
        )}
        {editeurCadrage && <EditeurCadrage etat={etat} agir={agir} />}

        <label className="interrupteur">
          <input type="checkbox" checked={etat.afficher_qr}
            onChange={(e) => agir("qr", e.target.checked ? { valeur: "telecommande" } : { valeur: false })} />
          Afficher le QR code sur l'écran
        </label>
      </Section>

      <Section titre="Clé USB">
        {etat.usb.presente ? (
          <>
            <p className="info">
              Clé détectée · {etat.usb.libre_go} Go libres. Chaque volée terminée y est enregistrée
              automatiquement, puis effacée du serveur.
            </p>
            <button className="bouton" disabled={etat.usb.sauvegarde.etat === "en_cours"}
              onClick={() => agir("sauvegarder_usb")}>
              Enregistrer maintenant (avant de retirer la clé)
            </button>
          </>
        ) : (
          <p className="info">
            Sans clé, seule la volée en cours est gardée pour le rejeu. Branchez une clé USB sur le
            serveur pour conserver chaque volée.
          </p>
        )}
        {etat.usb.sauvegarde.message && (
          <p className={`info ${etat.usb.sauvegarde.etat === "erreur" ? "info--erreur" : ""}`}>
            {etat.usb.sauvegarde.message}
          </p>
        )}
      </Section>

      <Section titre="Configuration">
        <AjoutCamera qrType={etat.qr_type} agir={agir} />
        {etat.disque?.libre_go != null && (
          <p className={`info ${espaceBas ? "info--erreur" : ""}`}>Espace libre sur le serveur : {etat.disque.libre_go} Go</p>
        )}
        <button
          className="bouton bouton--discret"
          onClick={async () => {
            setErreur(null);
            try {
              await recharger();
            } catch (e) {
              if (e.codeRequis) setCodeDemande(true);
              else setErreur(e.message);
            }
          }}
        >
          Recharger la configuration des caméras
        </button>
      </Section>
      </div>
      </div>
    </div>
  );
}
