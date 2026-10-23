# Feuille de route

## À valider sur le matériel

- [ ] Caméras USB réelles (MJPEG 720p30) sur Pi 5 : nombre maximal avec `libx264`.
- [ ] Caméra 100/120 i/s : charge et qualité du ralenti, sur Pi 5 et sur mini-PC N100 (`vaapi`).
- [ ] Nœud Pi Zero 2 W : stabilité Wi-Fi sur une séance complète.
- [ ] Nœud cible : réglage de la détection sur une vraie cible, en salle et en extérieur.
- [ ] Lecture sur iPad (Safari), Android, TV via boîtier HDMI.
- [ ] Détection du lâcher au micro dans une salle avec plusieurs archers.

## Fait

- Groupements (centre et dispersion) de la volée et de la séance, sur le mini-blason et dans `groupements.csv`.
- Comparaison de deux flèches, côte à côte ou superposées.
- Saisie manuelle du score depuis la télécommande.
- Annulation d'un faux lâcher.
- Stockage limité à la volée en cours, sauvegarde volée par volée sur la clé de l'archer.

## Prochaines fonctionnalités

- **Diagnostic des impacts** : règles indicatives selon la position des groupements (main d'arc, lâcher, ancrage), en miroir pour un gaucher. À n'afficher que sur un groupement, jamais sur une flèche isolée.
- **Double flux par caméra** : 720p pour la mosaïque, pleine définition pour les clips et la vue agrandie, pour soulager l'écran au-delà de 4 caméras.
- **Dessin sur le rejeu** : lignes d'alignement (épaules, bras d'arc) depuis la télécommande.
- **Multi-archers** : un profil par archer, séances rangées par archer.
- **Détection du lâcher par l'image** : en complément du micro, sur la vue de face à 100 i/s.
- **Mode solo** : une seule tablette avec sa propre caméra, sans serveur (MediaRecorder dans le navigateur).
- **Comparaison entre volées** : aujourd'hui limitée à la volée en cours, puisque les volées terminées quittent le serveur.
- **Lien avec un outil de réglage du matériel** (spine, puissance) pour relier groupements et réglages.
