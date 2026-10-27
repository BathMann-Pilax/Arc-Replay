# Utilisation

## Mise en route d'une séance

1. Allumer le serveur (et les nœuds) ; attendre une minute.
2. Connecter l'écran au Wi-Fi `ArcReplay` et ouvrir `http://10.42.0.1/`.
3. Avec le téléphone, scanner le QR code **1. Wi-Fi** en bas à droite de l'écran : il se connecte au réseau sans saisir le mot de passe.
4. Scanner ensuite le QR code **2. Télécommande** : la télécommande s'ouvre.
5. L'archer branche sa clé USB sur le serveur s'il veut garder ses vidéos.
6. Placer l'écran du bon côté, vérifier le retard, tirer.

Chaque démarrage du serveur ouvre une séance neuve et vide le serveur. En fin d'entraînement : bouton « Fin de séance ».

## L'écran

- **En haut à gauche** : état de la connexion, retard en cours (`−10 s`), volée et numéro de flèche.
- **En haut à droite** : mini-blason avec les impacts de la volée (si la détection est active) et le score de la dernière flèche.
- **Vue de la cible** (caméra `direct: true`) : en direct, sans retard, badge rouge **Direct**. « Direct ~ » : le WebRTC n'a pas pu s'établir, la vue passe par le HLS au bord du direct (2 à 3 s de retard) et le WebRTC est retenté toutes les 30 s. Les autres vues restent en différé.
- **En bas à droite** : QR code du Wi-Fi (si `wifi_ssid` est configuré, ce que fait `scripts/point-acces-wifi.sh`), puis QR code de la télécommande. Masquables depuis la télécommande.

L'écran ne demande aucune interaction : il suit la télécommande. Plusieurs écrans peuvent afficher la même chose.

Sur une tablette seule, ouvrez `http://10.42.0.1/?controles` : un bouton « Commandes » ouvre la télécommande dans un panneau latéral.

Sans serveur du tout, avec la caméra de la tablette ou du PC : voir le [mode solo](mode-solo.md).

## La télécommande

### Rejeu

- **Rejouer la dernière flèche** : toutes les vues de la flèche en boucle, synchronisées. Le bouton devient actif quelques secondes après le tir, le temps de découper les clips.
- **×1, ×0,5, ×0,25** : vitesse de lecture. Le ralenti est surtout utile avec la caméra 100/120 i/s.
- **Pause / Lecture, Recommencer**.
- **Retour au direct** : revient à la mosaïque en différé.
- **Liste des flèches** : choisir une volée (V1, V2…), puis une flèche pour la rejouer. Seules les flèches de la volée en cours ont encore leurs vidéos ; les volées terminées gardent leurs scores (grisées).
- **Comparer deux flèches** : toucher le bouton, puis deux flèches de la volée (une bonne, une mauvaise). L'écran les montre côte à côte sur une même caméra, alignées sur le lâcher. Pendant la comparaison : changer de caméra, ou passer en **Superposées** (la seconde en transparence par-dessus la première).

### Caméra cible

Section visible quand une caméra a un bloc `cadrage` (vue de la cible au pas de tir).

- **Miniature** en direct de la caméra.
- **▲ ◀ ▶ ▼** : déplacent la zone de 10 % de sa largeur. Maintenir appuyé pour déplacer en continu.
- **Zoom + / Zoom −** : ×1,25 par appui, de ×1 à ×8 ; le zoom actuel s'affiche au centre du pavé.
- **Vue complète** : revient au champ entier du capteur.

Le cadrage est fait dans le capteur par le Raspberry Pi : l'image reste nette et le flux n'est pas coupé. Il est gardé sur le Pi, même après un redémarrage. Si le Pi n'est pas connecté, les boutons sont grisés. Si vous recadrez une caméra qui a des lignes de repère, retracez-les.

### Score

Section masquée quand la détection est désactivée (`detection: false` sur la caméra cible) : ni score, ni blason, ni mini-blason.

- **Blason** : 122, 80, 80 réduit (5 à 10), 60, 40 cm, trispot 40 vertical ou triangulaire. Case **Arc à poulies** pour le 10 réduit. Changer de blason recalcule les scores détectés de la séance ; le choix est gardé pour les séances suivantes.
- **Trispot** : une seule flèche compte par spot. Une seconde flèche dans le même spot vaut M (la plus haute des deux), en gris sur le mini-blason. Le mini-blason superpose les trois spots, comme le calcul du groupement.
- **À confirmer** : un impact détecté sur une ligne (à moins de 1,5 mm) porte un **?** orange, sur l'écran et dans la liste des flèches. En touchant la flèche, la télécommande propose les deux valeurs possibles.

Pour noter une flèche quand la cible n'est pas filmée : toucher la flèche dans la liste (sinon c'est la dernière), puis **X, 10 … 1** ou **M** (manquée). Un score saisi remplace le score détecté ; la position mesurée, s'il y en a une, est gardée. Un score saisi n'est jamais modifié ensuite, ni par la règle du trispot ni par un changement de blason.

Dès deux impacts localisés par le nœud cible, le mini-blason de l'écran montre le **groupement** de la volée : une croix au centre et un cercle de dispersion. La télécommande indique son diamètre, pour la volée et pour la séance. Le fichier `groupements.csv` reprend le centre et la dispersion de chaque volée.

### Séance

- **Marquer un tir** : à utiliser sans micro. Le tir est daté une seconde avant l'appui.
- **Nouvelle volée** : force le passage à la volée suivante (sinon automatique après 6 flèches ou 90 s sans tir).
- **Annuler la dernière flèche** : retire un faux lâcher (le micro a pris le tir du voisin). Possible tant que la volée n'est pas terminée ; la flèche suivante reprend le numéro.
- **Fin de séance** : enregistre la volée en cours sur la clé (si elle est branchée), vide le serveur et repart à V1 F1. Attendez que le dernier clip soit prêt (le bouton est grisé pendant la découpe).

### Affichage

- **Retard** : de 3 à 30 s. Changement immédiat sur l'écran.
- **Droitier / Gaucher** : indique la latéralité de l'archer, enregistrée avec chaque flèche. Les images ne sont pas retournées automatiquement : le changement de côté est physique (écran sur support roulant, caméra de profil), voir [Changer de côté](#changer-de-côté-droitier--gaucher).
- **Caméras** : ↑ ↓ pour l'ordre, ⤢ pour agrandir une vue (les autres passent en bande latérale), ● / ○ pour masquer ou afficher, ⇆ pour retourner l'image en miroir (direct, rejeu et comparaison ; bouton bleu quand le miroir est actif).
- **Grille** : quadrillage (6 × 4) par-dessus toutes les vues, en direct et en rejeu.
- **Lignes de repère** : choisir une caméra, la télécommande affiche une image fixe de cette caméra ; toucher deux points trace une ligne (verticale du corps, ligne des épaules, niveau de l'ancrage…). Elle s'affiche sur l'écran avec son angle par rapport à l'horizontale, en direct, en rejeu et en comparaison, et reste en place si l'on active le miroir. Jusqu'à 8 lignes par caméra, effaçables une par une ; « Nouvelle image » rafraîchit la photo. Grille et lignes sont gardées d'une séance à l'autre : si une caméra bouge, retracez ses lignes.
- **Tablette** : dès 760 px de large (iPad, portrait compris), la télécommande s'affiche sur deux colonnes, le tir à gauche, les réglages à droite. Elle fonctionne aussi sur les anciens iPad (iPad 2, iOS 9).

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

## Ajouter une caméra depuis un téléphone

Pas besoin de caméra USB pour une vue supplémentaire : dans la télécommande, section « Configuration », bouton « Ajouter une caméra depuis un téléphone » affiche un QR code. Sur le téléphone (même Wi-Fi que le serveur) :

1. Scanner le QR code : la page s'ouvre en `https://`.
2. Premier accès : avertissement « connexion non privée » (certificat local, pas une vraie attaque) → « Avancé » puis « Continuer ».
3. Autoriser la caméra, donner un nom (ex. « tribune »), bouton « Démarrer ».

La vue apparaît dans la mosaïque de l'écran sous ce nom, utilisable comme les autres caméras (rejeu, clips). Bouton « Arrêter » sur le téléphone pour la retirer. Rien n'est installé : fermer l'onglet revient au même que de débrancher une caméra.

**Limite :** le flux dépend du réseau Wi-Fi (latence, qualité variable) ; à réserver aux vues secondaires, pas à la caméra de profil principale.

La même page propose aussi une case « Micro : détecter le tir » (décochable indépendamment de la caméra) : le téléphone écoute le claquement de corde et signale le lâcher au serveur, comme le ferait le micro branché sur le serveur (`detecteur-lacher`). Un curseur permet de régler le seuil sur place.

## Changer de côté (droitier / gaucher)

L'image n'est pas inversée : c'est le matériel qui change de côté.

- **Écran** : posé sur un support en bois à roulettes, on le pousse du côté vers lequel l'archer est tourné (côté visage et poitrine, le même que la caméra de profil), hors de la trajectoire des flèches et assez près pour lire le rejeu sans quitter sa position.
- **Caméra de profil** (et 3/4 face) : à déplacer aussi, elle doit filmer côté visage et poitrine.
- **Télécommande** : appuyer sur « Droitier » ou « Gaucher » pour que la latéralité soit notée dans les fichiers de la séance.

Conseils pour le support : roulettes avec frein pour qu'il ne bouge pas pendant la volée, pied assez large (ou lesté) pour ne pas basculer, écran fixé par une attache VESA, et une rallonge assez longue pour passer d'un côté à l'autre sans débrancher. Si l'écran est en Wi-Fi ou relié par un câble HDMI long, rien d'autre à reconnecter.

En salle, filmez à 100 i/s plutôt que 120 : à 120 i/s, l'éclairage sur secteur 50 Hz fait scintiller l'image.
