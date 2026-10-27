# Feuille de route

## À valider sur le matériel

- [ ] Mode solo sur iPad (Safari), tablette Android et PC : images par seconde en qualité Standard, export vidéo, micro en extérieur.
- [ ] Caméras USB réelles (MJPEG 720p30) sur Pi 5 : nombre maximal avec `libx264`.
- [ ] Caméra 100/120 i/s : charge et qualité du ralenti, sur Pi 5 et sur mini-PC N100 (`vaapi`).
- [ ] Nœud Pi Zero 2 W : stabilité Wi-Fi sur une séance complète.
- [ ] Vue cible en direct sur Pi 3 B+ : affichage en moins de 3 s, latence inférieure à 1 s, commande de cadrage visible en moins de 0,5 s sans coupure, cadrage conservé après redémarrage du service et du Pi, `vcgencmd get_throttled` à `0x0`, charge processeur.
- [ ] WebRTC sur iPad et TV : vérifier que le port 8189 passe (sinon repli HLS « Direct ~ »).
- [ ] Lecture sur iPad (Safari), Android, TV via boîtier HDMI.
- [ ] Détection du lâcher au micro dans une salle avec plusieurs archers.

## Fait

- Groupements (centre et dispersion) de la volée et de la séance, sur le mini-blason et dans `groupements.csv`.
- Comparaison de deux flèches, côte à côte ou superposées.
- Saisie manuelle du score depuis la télécommande.
- Annulation d'un faux lâcher.
- Stockage limité à la volée en cours, sauvegarde volée par volée sur la clé de l'archer.
- [Mode solo](mode-solo.md) : tablette ou PC seul avec sa propre caméra, installable et hors ligne.
- Blasons réduits et trispots (une flèche par spot), 10 réduit pour l'arc à poulies, impacts « à confirmer » près d'une ligne (moteur de score repris d'ArcAssist).
- Vue cible en direct (WebRTC) cadrée depuis la télécommande, serveur et caméra cible sur un seul Pi 3 B+.
- Grille et lignes de repère avec leur angle, tracées depuis la télécommande sur une image de la caméra, affichées en direct et en rejeu.

## Prochaines fonctionnalités

- **Détection d'impact (reportée)** : désactivée par `detection: false`, code conservé (mode `detection: true` du nœud cible, outils « vue de face » dans `noeuds/cible/outils/`). Pistes :
  - caméra dans le coffre d'éclairage avec un grand-angle, vue presque de face et rapprochée ;
  - repérage de l'encoche (bien visible) et correction par un décalage constant mesuré à l'installation ;
  - repérage des trous au retrait des flèches (image avant/après le retrait), sans tube pour masquer l'impact.
- **Diagnostic des impacts** : règles indicatives selon la position des groupements (main d'arc, lâcher, ancrage), en miroir pour un gaucher. À n'afficher que sur un groupement, jamais sur une flèche isolée.
- **Double flux par caméra** : 720p pour la mosaïque, pleine définition pour les clips et la vue agrandie, pour soulager l'écran au-delà de 4 caméras.
- **Dessin sur le rejeu** : tracés temporaires sur une image du rejeu (les lignes de repère permanentes existent déjà).
- **Multi-archers** : un profil par archer, séances rangées par archer.
- **Détection du lâcher par l'image** : en complément du micro, sur la vue de face à 100 i/s.
- **Comparaison entre volées** : aujourd'hui limitée à la volée en cours, puisque les volées terminées quittent le serveur.
- **Lien avec un outil de réglage du matériel** (spine, puissance) pour relier groupements et réglages.
