import { impactsPositionnes, positionSurCible } from "./logique";

// Blason World Archery avec les impacts de la volée en cours et, dès deux impacts,
// le centre et la dispersion du groupement.
// Blason réduit ou trispot : seul le spot imprimé est dessiné (zones zone_min à 10).
// Sur un trispot, les trois spots sont superposés : chaque impact est placé dans son
// spot, comme pour le calcul du groupement.
const COULEURS = ["#f4f1ea", "#1b1b1b", "#1f6fd1", "#d8322a", "#f2c230"]; // 1-2 … 9-10

export default function MiniCible({ impacts, groupement = null, blason = null, taille = 150 }) {
  const zoneMin = blason?.zone_min || 1;
  const largeur = 50 / (11 - zoneMin); // largeur d'une zone sur le dessin (rayon 50)
  const places = impactsPositionnes(impacts);
  const position = (imp) => positionSurCible(
    imp.rel_x_mm ?? imp.x_mm, imp.rel_y_mm ?? imp.y_mm, imp.diametre_mm, zoneMin);

  const zones = [];
  for (let z = zoneMin; z <= 10; z++) {
    const trait = z <= 2 ? "#999" : z <= 4 ? "#666" : "rgba(0,0,0,0.35)";
    zones.push(<circle key={z} cx="50" cy="50" r={(11 - z) * largeur}
      fill={COULEURS[Math.floor((z - 1) / 2)]} stroke={trait} strokeWidth="0.3" />);
  }
  const trispot = blason && blason.disposition !== "simple";
  return (
    <svg className="mini-cible" width={taille} height={taille} viewBox="-2 -2 104 104" role="img"
      aria-label={trispot ? "Impacts de la volée, trois spots superposés" : "Impacts de la volée en cours"}>
      {zones}
      {/* Cercle du X, ou 10 réduit d'un arc à poulies */}
      <circle cx="50" cy="50" r={largeur / 2} fill="none" stroke="rgba(0,0,0,0.4)" strokeWidth="0.3" />
      {places.map((imp, i) => {
        const { x, y } = position(imp);
        const derniere = i === places.length - 1;
        return (
          <circle key={i} cx={x} cy={y} r={derniere ? 3 : 2.2}
            fill={imp.double ? "#888" : derniere ? "#22e07a" : "#fff"} stroke="#000" strokeWidth="0.6" />
        );
      })}
      {groupement && places.length > 0 && (() => {
        const ref = places[places.length - 1];
        const { x, y, echelle } = positionSurCible(
          groupement.centre_x_mm, groupement.centre_y_mm, ref.diametre_mm, zoneMin);
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
