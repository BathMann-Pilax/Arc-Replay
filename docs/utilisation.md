# Utilisation

## Mise en route d'une séance

1. Allumer le serveur (et les nœuds) ; attendre une minute.
2. Connecter l'écran et le téléphone au Wi-Fi `ArcReplay`.
3. Ouvrir `http://10.42.0.1/` sur l'écran.
4. Scanner le QR code affiché en bas à droite avec le téléphone : la télécommande s'ouvre.
5. L'archer branche sa clé USB sur le serveur s'il veut garder ses vidéos.
6. Placer l'écran du bon côté, vérifier le retard, tirer.

Chaque démarrage du serveur ouvre une séance neuve et vide le serveur. En fin d'entraînement : bouton « Fin de séance ».

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
- **Liste des flèches** : choisir une volée (V1, V2…), puis une flèche pour la rejouer. Seules les flèches de la volée en cours ont encore leurs vidéos ; les volées terminées gardent leurs scores (grisées).
- **Comparer deux flèches** : toucher le bouton, puis deux flèches de la volée (une bonne, une mauvaise). L'écran les montre côte à côte sur une même caméra, alignées sur le lâcher. Pendant la comparaison : changer de caméra, ou passer en **Superposées** (la seconde en transparence par-dessus la première).

### Score

Pour noter une flèche quand la cible n'est pas filmée : toucher la flèche dans la liste (sinon c'est la dernière), puis **X, 10 … 1** ou **M** (manquée). Un score saisi remplace le score détecté ; la position mesurée, s'il y en a une, est gardée.

Dès deux impacts localisés par le nœud cible, le mini-blason de l'écran montre le **groupement** de la volée : une croix au centre et un cercle de dispersion. La télécommande indique son diamètre, pour la volée et pour la séance. Le fichier `groupements.csv` reprend le centre et la dispersion de chaque volée.

### Séance

- **Marquer un tir** : à utiliser sans micro. Le tir est daté une seconde avant l'appui.
- **Nouvelle volée** : force le passage à la volée suivante (sinon automatique après 6 flèches ou 90 s sans tir).
- **Annuler la dernière flèche** : retire un faux lâcher (le micro a pris le tir du voisin). Possible tant que la volée n'est pas terminée ; la flèche suivante reprend le numéro.
- **Fin de séance** : enregistre la volée en cours sur la clé (si elle est branchée), vide le serveur et repart à V1 F1. Attendez que le dernier clip soit prêt (le bouton est grisé pendant la découpe).

### Affichage

- **Retard** : de 3 à 30 s. Changement immédiat sur l'écran.
- **Droitier / Gaucher** : indique la latéralité de l'archer, enregistrée avec chaque flèche. Les images ne sont jamais retournées : le changement de côté est physique (écran sur support roulant, caméra de profil), voir [Changer de côté](#changer-de-côté-droitier--gaucher).
- **Caméras** : ↑ ↓ pour l'ordre, ⤢ pour agrandir une vue (les autres passent en bande latérale), ● / ○ pour masquer ou afficher.

### Clé USB : où vont les vidéos

Le serveur ne garde que **la volée en cours**, le temps du rejeu.

- **Sans clé** : à chaque nouvelle volée, les vidéos de la précédente sont effacées. À la fin de la séance, tout est effacé.
- **Avec la clé de l'archer** (exFAT, branchée sur le serveur) : chaque volée terminée est copiée sur la clé, puis effacée du serveur. La carte SD (ou le disque NVMe) ne se remplit donc jamais.
- **Enregistrer maintenant** : copie aussi la volée en cours. Attendez « Vous pouvez la retirer » avant de débrancher la clé.
- Une clé branchée en cours de séance reçoit les volées suivantes, pas celles déjà terminées.

Le serveur est aussi vidé à chaque redémarrage : une vidéo qui n'est pas sur la clé ne survit pas à une coupure de courant.

Contenu de la clé :

```
arc-replay/
  2026-10-23_18h41m05/
    seance.csv
    groupements.csv
    volee01/
      fleche1/
        V01_F1_profil.mp4
        V01_F1_face.mp4
        V01_F1_arriere.mp4
        V01_F1_cible.mp4
        V01_F1_impact.jpg
        impact.json
```

`seance.csv` et `groupements.csv` s'ouvrent directement dans Excel ou LibreOffice (séparateur `;`) : volée, flèche, heure, score, position de l'impact en mm.

## Conseils de prise de vue

| Vue | Placement |
|---|---|
| Profil | Côté visage et poitrine de l'archer, perpendiculaire à la ligne de tir, cadrage pied à tête et arc entier. Change de côté pour un gaucher. |
| Face (ralenti) | Devant l'archer, décalée hors de la ligne de tir, cadrée sur le haut du corps et la main de corde. |
| Arrière | Derrière l'archer, dans l'axe de la flèche : alignement épaules, bras d'arc, corde. |
| Dessus | Au plafond ou sur perche : alignement des épaules et de la flèche. |
| 3/4 face | Entre profil et face, côté visage : ancrage et tension du dos. |

## Code de la télécommande

Sur le Wi-Fi `ArcReplay`, protégé par mot de passe, il n'y a pas de code. Si le serveur est branché sur le réseau du club, réglez `code_telecommande` dans la configuration, puis ouvrez une fois l'écran avec `http://<serveur>/?code=<le code>` : le QR code affiché transmet le code au téléphone, qui le mémorise. Un appareil sans le code peut regarder, pas piloter ; la télécommande demande alors le code.

## Changer de côté (droitier / gaucher)

L'image n'est pas inversée : c'est le matériel qui change de côté.

- **Écran** : posé sur un support en bois à roulettes, on le pousse du côté vers lequel l'archer est tourné (côté visage et poitrine, le même que la caméra de profil), hors de la trajectoire des flèches et assez près pour lire le rejeu sans quitter sa position.
- **Caméra de profil** (et 3/4 face) : à déplacer aussi, elle doit filmer côté visage et poitrine.
- **Télécommande** : appuyer sur « Droitier » ou « Gaucher » pour que la latéralité soit notée dans les fichiers de la séance.

Conseils pour le support : roulettes avec frein pour qu'il ne bouge pas pendant la volée, pied assez large (ou lesté) pour ne pas basculer, écran fixé par une attache VESA, et une rallonge assez longue pour passer d'un côté à l'autre sans débrancher. Si l'écran est en Wi-Fi ou relié par un câble HDMI long, rien d'autre à reconnecter.

En salle, filmez à 100 i/s plutôt que 120 : à 120 i/s, l'éclairage sur secteur 50 Hz fait scintiller l'image.
