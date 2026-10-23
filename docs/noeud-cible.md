# Nœud cible

Le nœud cible est un Raspberry Pi 4 placé dans le coffre d'éclairage de la cible. Il envoie la vue de la cible à la mosaïque et, à chaque flèche, localise l'impact et l'envoie au serveur.

> **Statut : prototype.** La détection a été testée sur des images de synthèse. Elle doit être réglée sur votre cible réelle (angle, éclairage, couleur des tubes).

## Fonctionnement

1. Le nœud garde en mémoire les 20 dernières secondes d'images basse définition (640 × 480, 4 images par seconde).
2. Le serveur annonce une nouvelle flèche avec l'heure du lâcher.
3. 2,5 s après le lâcher, le nœud compare l'image prise juste avant le lâcher et l'image actuelle : seule la nouvelle flèche a changé.
4. Il garde la plus grande zone de changement à l'intérieur du blason, et prend son extrémité du côté configuré comme point d'entrée.
5. Une homographie, calibrée une fois, convertit ce point en millimètres depuis le centre.
6. Le serveur calcule le score (règle World Archery : une flèche qui touche une ligne compte la zone supérieure) et l'affiche.

Les flèches déjà plantées ne gênent pas : on compare toujours l'avant et l'après d'un même tir.

## Montage

- Caméra grand-angle (Camera Module 3 **Wide**) : la cible est très proche.
- Objectif hors du faisceau des lampes, derrière une vitre en polycarbonate.
- Fixation rigide : si la caméra bouge, il faut recalibrer.
- Antenne Wi-Fi tournée vers le pas de tir, loin des pièces métalliques de l'éclairage. Mieux : Ethernet avec carte PoE.
- Exposition stable : un éclairage de cible constant aide beaucoup (pas de nuages qui passent sur une cible en extérieur sans éclairage).

## Calibration

À faire à l'installation, puis à chaque changement de blason ou de position de caméra.

```bash
sudo systemctl stop arc-replay-cible
cd /opt/arc-replay/cible
sudo -u arc python3 calibrer.py capture --sortie blason.jpg
```

Récupérez `blason.jpg` (par `scp`) et ouvrez-le dans un logiciel qui affiche les coordonnées du pointeur (GIMP, Paint.NET, ou l'aperçu de nombreux visualiseurs). Relevez les pixels du **bord extérieur du blason** :

1. le point le plus haut ;
2. le point le plus à droite ;
3. le point le plus bas ;
4. le point le plus à gauche.

Puis :

```bash
sudo -u arc python3 calibrer.py points --diametre 1220 --image blason.jpg \
    322,41 598,252 318,463 40,249
```

`--diametre` vaut 400, 600, 800 ou 1220 selon le blason. Ouvrez `verification.jpg` : les cercles orange doivent tomber sur les limites des zones. Si c'est le cas :

```bash
sudo systemctl start arc-replay-cible
journalctl -u arc-replay-cible -f
```

## Réglages (`cible.yml`)

| Clé | Défaut | Rôle |
|---|---|---|
| `extremite` | `haut` | Côté de la zone détectée où se trouve l'entrée dans le blason. Le tube dépasse vers la caméra : caméra sous la cible → `haut`, au-dessus → `bas`, à gauche → `droite`, à droite → `gauche`. |
| `seuil` | `30` | Sensibilité. Baissez si des flèches ne sont pas vues, montez si du bruit est pris pour une flèche. |
| `aire_min` | `30` | Taille minimale d'une zone, en pixels. |
| `attente_apres_lacher_s` | `2.5` | Délai avant la photo « après » : temps de vol et vibration du tube. |
| `analyse_fps` | `4` | Fréquence des images d'analyse. |

Méthode de réglage de `extremite` : tirez quelques flèches, puis ouvrez les photos annotées `V01_F1_impact.jpg` (dans le dossier de la flèche, ou sur la clé après export). Le contour rouge entoure la flèche détectée, le rond vert marque le point retenu : il doit être là où le tube entre dans le blason. Sinon, changez `extremite` et relancez le service.

## Limites connues

- Deux flèches dans le même trou ou un « Robin Hood » : la zone de changement peut être mal interprétée.
- Ombre de l'archer qui va chercher ses flèches : les tirs suivants ne sont pas affectés (on compare avant/après chaque tir), mais une ombre qui passe pendant les 2,5 s d'attente peut fausser l'impact.
- Une flèche hors blason (paille) n'est pas comptée : le masque ignore tout ce qui est hors du blason.
- Le diagnostic de la cause probable d'un impact n'est pas encore implémenté (voir la [feuille de route](feuille-de-route.md)).
