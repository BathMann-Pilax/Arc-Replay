/**
 * Mémoire d'images horodatées (JPEG), dans l'ordre d'arrivée.
 *
 * Toutes les heures sont en millisecondes sur l'horloge performance.now().
 * Les clips gardent leurs propres références aux images : purger le tampon
 * ne les touche pas.
 */
export class Tampon {
  constructor() {
    this.images = []; // { t, blob, octets }
    this.octets = 0;
  }

  ajouter(t, blob) {
    // Un encodage peut finir après le suivant : on garde l'ordre des heures
    let i = this.images.length;
    while (i > 0 && this.images[i - 1].t > t) i--;
    this.images.splice(i, 0, { t, blob, octets: blob.size ?? 0 });
    this.octets += blob.size ?? 0;
  }

  /** Oublie les images plus anciennes que `limite`. */
  purger(limite) {
    let n = 0;
    while (n < this.images.length && this.images[n].t < limite) {
      this.octets -= this.images[n].octets;
      n++;
    }
    if (n) this.images.splice(0, n);
  }

  /** Dernière image prise au plus tard à l'heure `t` (null si aucune). */
  aLHeure(t) {
    let bas = 0;
    let haut = this.images.length - 1;
    let trouve = null;
    while (bas <= haut) {
      const m = (bas + haut) >> 1;
      if (this.images[m].t <= t) {
        trouve = this.images[m];
        bas = m + 1;
      } else {
        haut = m - 1;
      }
    }
    return trouve;
  }

  /** Images entre `debut` et `fin` (incluses), pour un clip. */
  extraire(debut, fin) {
    return this.images.filter((im) => im.t >= debut && im.t <= fin);
  }

  get duree() {
    const n = this.images.length;
    return n < 2 ? 0 : this.images[n - 1].t - this.images[0].t;
  }
}

/** Durée d'historique à garder : de quoi afficher en différé et découper un clip. */
export function dureeAGarder({ delai_s, avant_s, apres_s }) {
  return (Math.max(delai_s, avant_s + apres_s) + 3) * 1000;
}

/**
 * Image d'un clip à montrer après `ecoule` ms de lecture à vitesse 1.
 * Le clip boucle ; renvoie l'indice de l'image.
 */
export function indiceDansClip(images, ecoule) {
  if (!images.length) return -1;
  const debut = images[0].t;
  const duree = images[images.length - 1].t - debut;
  const pos = duree > 0 ? debut + (((ecoule % duree) + duree) % duree) : debut;
  let bas = 0;
  let haut = images.length - 1;
  let trouve = 0;
  while (bas <= haut) {
    const m = (bas + haut) >> 1;
    if (images[m].t <= pos) {
      trouve = m;
      bas = m + 1;
    } else {
      haut = m - 1;
    }
  }
  return trouve;
}
