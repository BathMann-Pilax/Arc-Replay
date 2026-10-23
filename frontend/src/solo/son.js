/** Niveau crête d'un bloc audio (-1..1), en dBFS. */
export function niveauDbfs(bloc) {
  let crete = 0;
  for (let i = 0; i < bloc.length; i++) {
    const v = Math.abs(bloc[i]);
    if (v > crete) crete = v;
  }
  return 20 * Math.log10(Math.max(crete, 1e-6));
}

/** Claquement de corde : niveau au-dessus du seuil, hors période d'anti-rebond. */
export class DetecteurLacher {
  constructor(seuil_db = -20, anti_rebond_ms = 2000) {
    this.seuil_db = seuil_db;
    this.anti_rebond_ms = anti_rebond_ms;
    this.dernier = -Infinity;
  }

  bloc(niveau, t) {
    if (niveau >= this.seuil_db && t - this.dernier >= this.anti_rebond_ms) {
      this.dernier = t;
      return true;
    }
    return false;
  }
}
