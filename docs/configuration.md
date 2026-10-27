# Configuration

Tout se règle dans `config/arc-replay.yml`. Après une modification : bouton **Recharger la configuration des caméras** dans la télécommande, ou `docker compose restart backend`.

## `serveur`

| Clé | Défaut | Rôle |
|---|---|---|
| `delai_s` | `10` | Retard d'affichage au démarrage (3 à 30 s). Modifiable ensuite depuis la télécommande. |
| `lateralite` | `droitier` | `droitier` ou `gaucher` au démarrage. Simple information (enregistrée avec chaque flèche) : aucune image n'est retournée. |
| `usb_chemin` | `/media/hote/arc-usb` | Point de montage de la clé, vu depuis le conteneur (`/media/arc-usb` sur l'hôte). |
| `usb_verifier_montage` | `true` | `false` pour tester la sauvegarde vers un simple dossier. |
| `code_telecommande` | vide | Code exigé pour piloter depuis la télécommande. Inutile sur le Wi-Fi `ArcReplay` protégé par mot de passe ; conseillé si le serveur est branché sur le réseau du club. Voir [Code de la télécommande](utilisation.md#code-de-la-télécommande). |
| `alerte_espace_go` | `2` | En dessous de cet espace libre sur le serveur (Go), la télécommande affiche une alerte. |
| `enregistrements` | `/recordings` | Enregistrements bruts de MediaMTX, vidés au démarrage et en fin de séance. |
| `wifi_ssid`, `wifi_mot_de_passe` | vides | Wi-Fi du serveur. Renseignés, l'écran affiche un QR code « 1. Wi-Fi » à côté de celui de la télécommande : le téléphone se connecte sans saisir le mot de passe. `scripts/point-acces-wifi.sh` les remplit tout seul. |
| `adresse_publique` | `http://10.42.0.1` | Adresse du serveur pour les téléphones. Sert au QR code quand l'écran est ouvert sur le serveur lui-même (`http://localhost/`). |

## `volees`

| Clé | Défaut | Rôle |
|---|---|---|
| `fleches_par_volee` | `6` | Une fois la volée pleine, la flèche suivante ouvre une nouvelle volée. |
| `nouvelle_apres_s` | `90` | Pause sans tir au-delà de laquelle on change de volée (le temps d'aller aux cibles). |

Le bouton « Nouvelle volée » de la télécommande force le changement.

## `clips`

| Clé | Défaut | Rôle |
|---|---|---|
| `avant_s` | `6` | Secondes gardées avant le lâcher (préparation, armement, visée). |
| `apres_s` | `3` | Secondes gardées après le lâcher (suivi). |
| `marge_s` | `2` | Attente supplémentaire avant la découpe, le temps que les enregistrements soient écrits. |

Un clip est donc disponible environ `apres_s + marge_s` secondes après le tir.

## `lacher`

| Clé | Défaut | Rôle |
|---|---|---|
| `anti_rebond_s` | `2` | Un second lâcher signalé moins de 2 s après le précédent est ignoré. |
| `decalage_manuel_s` | `1.0` | Avec le bouton « Marquer un tir », le tir est daté 1 s avant l'appui. |

## `blason`

Blason utilisé pour calculer le score des impacts détectés. C'est la valeur au premier démarrage : ensuite, le blason choisi dans la télécommande (section Score) est gardé d'une séance à l'autre. Changer de blason recalcule les scores détectés de la séance.

| Clé | Défaut | Rôle |
|---|---|---|
| `diametre_mm` | `1220` | Diamètre du blason complet de référence : `400` pour un 40 cm comme pour un trispot 40. |
| `zone_min` | `1` | Zone la plus basse imprimée : `1` blason complet, `5` pour le 80 cm réduit, `6` pour un trispot. Au-delà, la flèche vaut M. |
| `disposition` | `simple` | `simple`, `trispot_vertical` (trois spots l'un au-dessus de l'autre) ou `trispot_triangle`. |
| `ecart_mm` | `220` | Trispot : distance entre les centres des spots. |
| `poulies` | `false` | Arc à poulies : 10 réduit (le 10 se limite au cercle intérieur, le reste du 10 vaut 9). |

Règles appliquées (World Archery) : une flèche qui touche une ligne compte la zone supérieure, la distance étant mesurée depuis le bord du tube. Sur un trispot, une seule flèche compte par spot : si deux flèches sont dans le même spot, la plus haute vaut M. Un impact détecté à moins de 1,5 mm d'une ligne est marqué **à confirmer** : la télécommande propose les deux valeurs.

Sur un trispot, le nœud cible envoie la position de l'impact depuis le centre du spot du milieu ; le serveur retrouve le spot touché.

## `cameras`

L'ordre de la liste est l'ordre par défaut de la mosaïque ; il se change ensuite depuis la télécommande.

### Champs communs

| Clé | Obligatoire | Rôle |
|---|---|---|
| `id` | oui | Identifiant court : minuscules, chiffres, `-` et `_`. Sert dans les noms de fichiers (`V01_F2_<id>.mp4`). |
| `nom` | oui | Nom affiché. |
| `type` | oui | `usb`, `reseau` ou `rtsp`. |
| `ralenti` | non | Signale une caméra rapide (badge « 100 i/s » à l'écran). |

### Caméra USB (`type: usb`)

| Clé | Défaut | Rôle |
|---|---|---|
| `peripherique` | — | Chemin `/dev/v4l/by-id/…-video-index0`. |
| `format_entree` | `mjpeg` | `mjpeg`, `h264` ou `yuyv422` (brut : réservé aux petites résolutions). |
| `largeur`, `hauteur` | `1280`, `720` | Résolution demandée à la caméra. |
| `fps` | `30` | Cadence demandée. Aussi l'intervalle entre images clés. |
| `encodeur` | `libx264` | Voir ci-dessous. |
| `debit` | `4M` | Débit vidéo (`4M`, `2500k`…). Comptez 4 Mbit/s en 720p30, 10 Mbit/s en 720p100. |

| Encodeur | Quand l'utiliser |
|---|---|
| `libx264` | Par défaut, partout. Coûteux en processeur : sur Pi 5, environ 2 à 3 caméras 720p30. |
| `copy` | La caméra sort déjà du H.264 (`format_entree: h264`) : aucun calcul. |
| `vaapi` | Mini-PC Intel (N100…) : encodage matériel, nombreuses caméras et 100 i/s possibles. |
| `v4l2m2m` | Raspberry Pi 4 utilisé comme serveur : encodeur matériel du Pi 4. |

### Nœud Raspberry Pi (`type: reseau`)

C'est le nœud qui publie vers `rtsp://<serveur>:8554/<id>`. L'`id` doit être celui passé à `installer.sh`.

| Champ | Défaut | Rôle |
|---|---|---|
| `direct` | `false` | Vue affichée **en direct** sur l'écran (WebRTC, latence inférieure à 1 s) au lieu du différé. Pour la vue de la cible. Repli automatique sur le HLS au bord du direct si le WebRTC échoue. |
| `detection` | absent | `false` sur la caméra cible : détection d'impact et score désactivés partout (routes, état, télécommande, écran). |
| `cadrage` | absent | Présent : le cadrage se règle depuis la télécommande (section « Caméra cible »). Sous-clés ci-dessous. `recadrage: true` (ancien nom) équivaut à un bloc vide. |
| `cadrage.zoom_max` | `8` | Zoom maximal ; zoom 1 = plus grande zone 16:9 du capteur. |
| `cadrage.pas_zoom` | `1.25` | Chaque « zoom + » multiplie le zoom par ce pas. |
| `cadrage.pas_deplacement` | `0.10` | Chaque flèche déplace la zone de 10 % de sa largeur visible. |
| `capteur` | `complet` | `complet` : pleine définition 4056 × 3040 (caméra HQ) à 10 i/s, net même en zoomant fort ; `binne` : 2028 × 1520 à 30 i/s. |
| `largeur`, `hauteur` | `1280`, `720` | Image envoyée par le nœud (1920 × 1080 conseillé pour la cible). |
| `fps` | selon `capteur` | 10 i/s en `complet`, 30 i/s en `binne`, sauf si indiqué. |
| `debit` | `4M` | Débit H.264 du nœud. |

Ces réglages sont envoyés au nœud à sa connexion, et de nouveau après « Recharger la configuration » (le nœud redémarre sa caméra si le capteur, la taille, la cadence ou le débit changent). Le cadrage lui-même est enregistré sur le nœud (`/var/lib/arc-replay/cadrage-<id>.json`) et restauré au redémarrage.

### Caméra IP (`type: rtsp`)

| Clé | Rôle |
|---|---|
| `url` | Adresse RTSP de la caméra, par exemple `rtsp://utilisateur:motdepasse@10.42.0.50:554/stream1`. |

Réglez dans la caméra elle-même une image clé par seconde (« I-frame interval » = cadence) pour un retard précis.

### Caméras ajoutées depuis un téléphone

Les caméras ouvertes depuis `/camera` (voir [Ajouter une caméra depuis un téléphone](utilisation.md#ajouter-une-caméra-depuis-un-téléphone)) n'apparaissent pas ici : elles sont créées à la volée (identifiants `tel-xxxxxx`), gardées en mémoire tant qu'elles publient, et ne survivent pas à un redémarrage du back-end.

## Exemple : ajouter une vue du dessus et une vue 3/4 face

```yaml
cameras:
  # … caméras existantes …
  - id: dessus
    nom: Dessus
    type: reseau          # Pi Zero 2 W fixé au plafond

  - id: trois-quarts
    nom: 3/4 face
    type: usb
    peripherique: /dev/v4l/by-id/usb-Arducam_USB_Camera_SN0001-video-index0
    largeur: 1280
    hauteur: 720
    fps: 30
```

## Variables d'environnement (`.env`)

Voir `.env.exemple` : fuseau horaire, port de l'interface, registre d'images, version de MediaMTX, seuil du micro.

## MediaMTX

`mediamtx/mediamtx.yml` règle la fenêtre HLS (40 s), l'enregistrement continu (purgé après 3 h) et active l'API et la relecture. Les chemins des caméras n'y figurent pas : le back-end les crée au démarrage. N'y touchez que pour allonger la purge (`recordDeleteAfter`) ou augmenter le retard maximal (`hlsSegmentCount` doit dépasser le retard voulu de quelques secondes).
