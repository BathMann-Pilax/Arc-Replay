// Volées et flèches du mode solo : mêmes règles que le serveur, en mémoire seulement.

export const REGLES = { fleches_par_volee: 6, nouvelle_apres_s: 90, anti_rebond_s: 2 };

export const seanceVide = () => ({ volee: 1, fleche: 0, fleches: [] });

/**
 * Enregistre un tir à l'heure `t` (ms). Renvoie { seance, fleche } ou null (anti-rebond).
 * Au changement de volée, les flèches de la précédente sont oubliées (mémoire libérée),
 * comme sur le serveur sans clé USB.
 */
export function tirer(seance, t, regles = REGLES) {
  let { volee, fleche, fleches } = seance;
  const precedente = fleches.at(-1) ?? seance.dernier;
  if (precedente) {
    const ecart = (t - precedente.t) / 1000;
    if (ecart >= 0 && ecart < regles.anti_rebond_s) return null;
    if (fleche > 0 && (fleche >= regles.fleches_par_volee || ecart > regles.nouvelle_apres_s)) {
      volee += 1;
      fleche = 0;
      fleches = [];
    }
  }
  fleche += 1;
  const nouvelle = { id: `V${String(volee).padStart(2, "0")}_F${fleche}`, volee, numero: fleche, t, images: null };
  return { seance: { volee, fleche, fleches: [...fleches, nouvelle], dernier: nouvelle }, fleche: nouvelle };
}

export function nouvelleVolee(seance) {
  if (seance.fleche === 0) return seance;
  return { volee: seance.volee + 1, fleche: 0, fleches: [], dernier: seance.dernier };
}

export function annulerDerniere(seance) {
  if (!seance.fleches.length) return seance;
  const fleches = seance.fleches.slice(0, -1);
  return { ...seance, fleche: seance.fleche - 1, fleches, dernier: fleches.at(-1) ?? null };
}

/** Range les images d'un clip dans la flèche (si elle est toujours là). */
export function avecImages(seance, id, images) {
  return { ...seance, fleches: seance.fleches.map((f) => (f.id === id ? { ...f, images } : f)) };
}
