import { angleRepere } from "./logique";

/**
 * Grille et lignes de repère dessinées par-dessus une vidéo ou une image.
 *
 * Le SVG a la taille réelle de l'image (viewBox) et le même cadrage que
 * `object-fit: contain` : les lignes restent collées à l'image, bandes noires comprises.
 * Les points sont en 0–1 dans l'image non retournée ; en miroir, on les retourne ici
 * (et pas avec une transformation CSS, qui mettrait aussi le texte à l'envers).
 */
export default function Reperes({ largeur, hauteur, lignes = [], grille = false, miroir = false, point = null }) {
  if (!largeur || !hauteur || (!grille && !lignes.length && !point)) return null;
  const X = (x) => (miroir ? 1 - x : x) * largeur;
  const Y = (y) => y * hauteur;
  const epaisseur = Math.max(2, largeur / 320);
  const police = Math.max(14, hauteur / 26);

  const quadrillage = [];
  if (grille) {
    for (let i = 1; i < 6; i++) quadrillage.push(`M${(largeur * i) / 6} 0V${hauteur}`);
    for (let i = 1; i < 4; i++) quadrillage.push(`M0 ${(hauteur * i) / 4}H${largeur}`);
  }

  return (
    <svg className="reperes" viewBox={`0 0 ${largeur} ${hauteur}`} preserveAspectRatio="xMidYMid meet"
      aria-hidden="true">
      {grille && <path d={quadrillage.join("")} stroke="rgba(255,255,255,0.35)" strokeWidth={epaisseur / 2} />}
      {lignes.map((l, i) => {
        const [x1, y1, x2, y2] = [X(l[0]), Y(l[1]), X(l[2]), Y(l[3])];
        return (
          <g key={i}>
            <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#000" strokeOpacity="0.5"
              strokeWidth={epaisseur * 2.2} strokeLinecap="round" />
            <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#4fd1c5" strokeWidth={epaisseur} strokeLinecap="round" />
            <text x={(x1 + x2) / 2 + police * 0.4} y={(y1 + y2) / 2 - police * 0.4} fontSize={police}
              fill="#4fd1c5" stroke="#000" strokeWidth={police / 8} paintOrder="stroke" fontWeight="700">
              {angleRepere(l, largeur, hauteur)}°
            </text>
          </g>
        );
      })}
      {point && <circle cx={X(point[0])} cy={Y(point[1])} r={epaisseur * 3} fill="#fff" stroke="#000"
        strokeWidth={epaisseur / 2} />}
    </svg>
  );
}
