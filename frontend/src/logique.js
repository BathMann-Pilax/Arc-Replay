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
export function positionSurCible(x_mm, y_mm, diametre_mm, zoneMin = 1) {
  const echelle = 50 / rayonImprime(diametre_mm, zoneMin);
  return { x: 50 + x_mm * echelle, y: 50 - y_mm * echelle, echelle };
}

/** Rayon imprimé d'un spot : un blason réduit ou un trispot s'arrête avant la zone 1. */
export const rayonImprime = (diametre_mm, zoneMin = 1) => ((11 - zoneMin) * diametre_mm) / 20;

/** Blasons proposés dans la télécommande (mêmes dimensions que dans ArcAssist). */
export const BLASONS = [
  { nom: "122 cm", blason: { diametre_mm: 1220, zone_min: 1, disposition: "simple" } },
  { nom: "80 cm", blason: { diametre_mm: 800, zone_min: 1, disposition: "simple" } },
  { nom: "80 cm réduit (5 à 10)", blason: { diametre_mm: 800, zone_min: 5, disposition: "simple" } },
  { nom: "60 cm", blason: { diametre_mm: 600, zone_min: 1, disposition: "simple" } },
  { nom: "40 cm", blason: { diametre_mm: 400, zone_min: 1, disposition: "simple" } },
  { nom: "Trispot 40 vertical", blason: { diametre_mm: 400, zone_min: 6, disposition: "trispot_vertical", ecart_mm: 220 } },
  { nom: "Trispot 40 triangulaire", blason: { diametre_mm: 400, zone_min: 6, disposition: "trispot_triangle", ecart_mm: 220 } },
];

/** Index du blason prédéfini qui correspond à celui de la séance, -1 sinon. */
export function indexBlason(b) {
  if (!b) return -1;
  return BLASONS.findIndex(({ blason: p }) => p.diametre_mm === b.diametre_mm
    && p.zone_min === b.zone_min && p.disposition === b.disposition
    && (p.disposition === "simple" || p.ecart_mm === b.ecart_mm));
}

/** Score saisi pour un libellé « X », « 10 »… « M » : paramètres de la commande `score`. */
export function valeurScore(libelle) {
  if (libelle === "X") return { valeur: 10, x: true };
  if (libelle === "M") return { valeur: 0, x: false };
  return { valeur: Number(libelle), x: false };
}

/**
 * Angle d'une ligne de repère par rapport à l'horizontale, de 0 à 90°.
 * Les points sont en 0–1 : il faut la taille de l'image pour un angle juste.
 */
export function angleRepere([x1, y1, x2, y2], largeur, hauteur) {
  const dx = Math.abs(x2 - x1) * largeur;
  const dy = Math.abs(y2 - y1) * hauteur;
  return Math.round((Math.atan2(dy, dx) * 180) / Math.PI);
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
