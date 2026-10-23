import { impactsPositionnes, positionSurCible } from "./logique";

// Blason World Archery à 10 zones, avec les impacts de la volée en cours
// et, dès deux impacts, le centre et la dispersion du groupement.
const COULEURS = [
  ["#f4f1ea", "#f4f1ea"], // 1-2 blanc
  ["#1b1b1b", "#1b1b1b"], // 3-4 noir
  ["#1f6fd1", "#1f6fd1"], // 5-6 bleu
  ["#d8322a", "#d8322a"], // 7-8 rouge
  ["#f2c230", "#f2c230"], // 9-10 or
];

export default function MiniCible({ impacts, groupement = null, taille = 150 }) {
  const places = impactsPositionnes(impacts);
  const zones = [];
  for (let z = 1; z <= 10; z++) {
    const r = (11 - z) * 5; // rayon sur 50
    const couleur = COULEURS[Math.floor((z - 1) / 2)][0];
    const trait = z <= 2 ? "#999" : z <= 4 ? "#666" : "rgba(0,0,0,0.35)";
    zones.push(<circle key={z} cx="50" cy="50" r={r} fill={couleur} stroke={trait} strokeWidth="0.3" />);
  }
  return (
    <svg className="mini-cible" width={taille} height={taille} viewBox="-2 -2 104 104" role="img"
      aria-label="Impacts de la volée en cours">
      {zones}
      <circle cx="50" cy="50" r="2.5" fill="none" stroke="rgba(0,0,0,0.4)" strokeWidth="0.3" />
      {places.map((imp, i) => {
        const { x, y } = positionSurCible(imp.x_mm, imp.y_mm, imp.diametre_mm);
        const derniere = i === places.length - 1;
        return (
          <circle key={i} cx={x} cy={y} r={derniere ? 3 : 2.2} fill={derniere ? "#22e07a" : "#fff"}
            stroke="#000" strokeWidth="0.6" />
        );
      })}
      {groupement && places.length > 0 && (() => {
        const ref = places[places.length - 1];
        const { x, y, echelle } = positionSurCible(groupement.centre_x_mm, groupement.centre_y_mm, ref.diametre_mm);
        const r = Math.max(groupement.dispersion_mm * echelle, 1.5);
        return (
          <g className="groupement" stroke="#00e5ff" strokeWidth="0.8" fill="none">
            <circle cx={x} cy={y} r={r} strokeDasharray="2 1.5" />
            <path d={`M${x - 2.5} ${y}h5M${x} ${y - 2.5}v5`} />
          </g>
        );
      })()}
    </svg>
  );
}
