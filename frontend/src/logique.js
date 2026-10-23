// Fonctions pures de l'interface, testées par Vitest (src/logique.test.js).

/** Caméras affichées, dans l'ordre choisi depuis la télécommande. */
export function camerasVisibles(etat) {
  const parId = Object.fromEntries(etat.cameras.map((c) => [c.id, c]));
  return etat.disposition.ordre
    .filter((id) => parId[id] && !etat.disposition.masquees.includes(id))
    .map((id) => parId[id]);
}

/** Nombre de colonnes de la mosaïque selon le nombre de vues. */
export function colonnesPour(n) {
  if (n <= 1) return 1;
  if (n <= 4) return 2;
  return 3;
}

/** Adresse d'un fichier de séance servi par nginx (chaque segment encodé). */
export const urlFichier = (relatif) => `/fichiers/${relatif.split("/").map(encodeURIComponent).join("/")}`;

/** Texte du score d'un impact : « X », « M » pour un manqué, « – » sans score. */
export function libelleScore(impact) {
  if (!impact || impact.score == null) return "–";
  if (impact.x) return "X";
  return impact.score === 0 ? "M" : String(impact.score);
}

/** Impacts dont la position est connue (les scores saisis à la main n'en ont pas). */
export const impactsPositionnes = (impacts) =>
  impacts.filter((i) => i && i.x_mm != null && i.y_mm != null && i.diametre_mm);

/**
 * Position sur le mini-blason (repère SVG 0..100, centre en 50,50).
 * Le y du blason va vers le haut, celui du SVG vers le bas.
 */
export function positionSurCible(x_mm, y_mm, diametre_mm) {
  const echelle = 50 / (diametre_mm / 2);
  return { x: 50 + x_mm * echelle, y: 50 - y_mm * echelle, echelle };
}

/** Flèches qu'on peut rejouer : leurs clips sont encore sur le serveur. */
export const rejouable = (f) => !!f && !f.archivee && Object.keys(f.clips || {}).length > 0;

/** Caméras présentes dans les clips des deux flèches comparées, dans l'ordre d'affichage. */
export function camerasCommunes(etat, a, b) {
  if (!a || !b) return [];
  return camerasVisibles(etat).filter((c) => a.clips[c.id] && b.clips[c.id]);
}

/** Lit le code de la télécommande dans l'adresse (?code=…), sinon celui mémorisé. */
export function codeDepuisAdresse(recherche, memorise) {
  const code = new URLSearchParams(recherche).get("code");
  return code || memorise || "";
}

/** Adresse de la télécommande encodée dans le QR code de l'écran. */
export function adresseTelecommande(origine, code) {
  return code ? `${origine}/telecommande?code=${encodeURIComponent(code)}` : `${origine}/telecommande`;
}
