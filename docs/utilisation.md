# Utilisation

## Mise en route d'une séance

1. Allumer le serveur (et les nœuds) ; attendre une minute.
2. Connecter l'écran et le téléphone au Wi-Fi `ArcReplay`.
3. Ouvrir `http://10.42.0.1/` sur l'écran.
4. Scanner le QR code affiché en bas à droite avec le téléphone : la télécommande s'ouvre.
5. Choisir droitier ou gaucher, vérifier le retard, tirer.

Une nouvelle séance s'ouvre automatiquement si la précédente date de plus de 6 heures. Sinon : bouton « Nouvelle séance ».

## L'écran

- **En haut à gauche** : état de la connexion, retard en cours (`−10 s`), volée et numéro de flèche.
- **En haut à droite** : mini-blason avec les impacts de la volée (si le nœud cible est installé) et le score de la dernière flèche.
- **En bas à droite** : QR code de la télécommande (masquable depuis la télécommande).

L'écran ne demande aucune interaction : il suit la télécommande. Plusieurs écrans peuvent afficher la même chose.

Sur une tablette seule, ouvrez `http://10.42.0.1/?controles` : un bouton « Commandes » ouvre la télécommande dans un panneau latéral.

## La télécommande

### Rejeu

- **Rejouer la dernière flèche** : toutes les vues de la flèche en boucle, synchronisées. Le bouton devient actif quelques secondes après le tir, le temps de découper les clips.
- **×1, ×0,5, ×0,25** : vitesse de lecture. Le ralenti est surtout utile avec la caméra 100/120 i/s.
- **Pause / Lecture, Recommencer**.
- **Retour au direct** : revient à la mosaïque en différé.
- **Liste des flèches** : choisir une volée (V1, V2…), puis une flèche pour la rejouer. Le score s'affiche si l'impact a été détecté.

### Séance

- **Marquer un tir** : à utiliser sans micro. Le tir est daté une seconde avant l'appui.
- **Nouvelle volée** : force le passage à la volée suivante (sinon automatique après 6 flèches ou 90 s sans tir).
- **Nouvelle séance** : range la séance en cours et repart à V1 F1.

### Affichage

- **Retard** : de 3 à 30 s. Changement immédiat sur l'écran.
- **Droitier / Gaucher** : indique la latéralité de l'archer, enregistrée avec chaque flèche. Les images ne sont jamais retournées : le changement de côté est physique (écran sur support roulant, caméra de profil), voir [Changer de côté](#changer-de-côté-droitier--gaucher).
- **Caméras** : ↑ ↓ pour l'ordre, ⤢ pour agrandir une vue (les autres passent en bande latérale), ● / ○ pour masquer ou afficher.

### Clé USB

Branchez une clé exFAT sur le serveur : la télécommande affiche « Clé détectée ».

- **Exporter la séance** : copie la séance en cours.
- **Tout exporter** : copie toutes les séances encore sur le serveur.

Les fichiers déjà présents sur la clé ne sont pas recopiés : on peut exporter après chaque volée. Attendez le message « Vous pouvez retirer la clé » avant de la débrancher.

Contenu de la clé :

```
arc-replay/
  2026-10-23_18h41/
    seance.csv
    volee01/
      fleche1/
        V01_F1_profil.mp4
        V01_F1_face.mp4
        V01_F1_arriere.mp4
        V01_F1_cible.mp4
        V01_F1_impact.jpg
        impact.json
```

`seance.csv` s'ouvre directement dans Excel ou LibreOffice (séparateur `;`) : volée, flèche, heure, score, position de l'impact en mm.

## Conseils de prise de vue

| Vue | Placement |
|---|---|
| Profil | Côté visage et poitrine de l'archer, perpendiculaire à la ligne de tir, cadrage pied à tête et arc entier. Change de côté pour un gaucher. |
| Face (ralenti) | Devant l'archer, décalée hors de la ligne de tir, cadrée sur le haut du corps et la main de corde. |
| Arrière | Derrière l'archer, dans l'axe de la flèche : alignement épaules, bras d'arc, corde. |
| Dessus | Au plafond ou sur perche : alignement des épaules et de la flèche. |
| 3/4 face | Entre profil et face, côté visage : ancrage et tension du dos. |

## Changer de côté (droitier / gaucher)

L'image n'est pas inversée : c'est le matériel qui change de côté.

- **Écran** : posé sur un support en bois à roulettes, on le pousse du côté vers lequel l'archer est tourné (côté visage et poitrine, le même que la caméra de profil), hors de la trajectoire des flèches et assez près pour lire le rejeu sans quitter sa position.
- **Caméra de profil** (et 3/4 face) : à déplacer aussi, elle doit filmer côté visage et poitrine.
- **Télécommande** : appuyer sur « Droitier » ou « Gaucher » pour que la latéralité soit notée dans les fichiers de la séance.

Conseils pour le support : roulettes avec frein pour qu'il ne bouge pas pendant la volée, pied assez large (ou lesté) pour ne pas basculer, écran fixé par une attache VESA, et une rallonge assez longue pour passer d'un côté à l'autre sans débrancher. Si l'écran est en Wi-Fi ou relié par un câble HDMI long, rien d'autre à reconnecter.

En salle, filmez à 100 i/s plutôt que 120 : à 120 i/s, l'éclairage sur secteur 50 Hz fait scintiller l'image.
