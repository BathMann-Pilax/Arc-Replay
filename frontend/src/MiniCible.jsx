// Blason World Archery à 10 zones, avec les impacts de la volée en cours.
const COULEURS = [
  ["#f4f1ea", "#f4f1ea"], // 1-2 blanc
  ["#1b1b1b", "#1b1b1b"], // 3-4 noir
  ["#1f6fd1", "#1f6fd1"], // 5-6 bleu
  ["#d8322a", "#d8322a"], // 7-8 rouge
  ["#f2c230", "#f2c230"], // 9-10 or
];

export default function MiniCible({ impacts, taille = 150 }) {
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
      {impacts.map((imp, i) => {
        const echelle = 50 / (imp.diametre_mm / 2);
        const x = 50 + imp.x_mm * echelle;
        const y = 50 - imp.y_mm * echelle; // y vers le haut sur le blason
        const derniere = i === impacts.length - 1;
        return (
          <g key={i}>
            <circle cx={x} cy={y} r={derniere ? 3 : 2.2} fill={derniere ? "#22e07a" : "#fff"}
              stroke="#000" strokeWidth="0.6" />
          </g>
        );
      })}
    </svg>
  );
}
