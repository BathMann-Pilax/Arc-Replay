# Configuration

Tout se règle dans `config/arc-replay.yml`. Après une modification : bouton **Recharger la configuration des caméras** dans la télécommande, ou `docker compose restart backend`.

## `serveur`

| Clé | Défaut | Rôle |
|---|---|---|
| `delai_s` | `10` | Retard d'affichage au démarrage (1 à 30 s). Modifiable ensuite depuis la télécommande. |
| `lateralite` | `droitier` | `droitier` ou `gaucher` au démarrage. Simple information (enregistrée avec chaque flèche) : aucune image n'est retournée. |
| `usb_chemin` | `/media/hote/arc-usb` | Point de montage de la clé, vu depuis le conteneur (`/media/arc-usb` sur l'hôte). |
| `usb_verifier_montage` | `true` | `false` pour tester l'export vers un simple dossier. |

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

Aucun autre champ : c'est le nœud qui publie vers `rtsp://<serveur>:8554/<id>`. L'`id` doit être celui passé à `installer.sh`.

### Caméra IP (`type: rtsp`)

| Clé | Rôle |
|---|---|
| `url` | Adresse RTSP de la caméra, par exemple `rtsp://utilisateur:motdepasse@10.42.0.50:554/stream1`. |

Réglez dans la caméra elle-même une image clé par seconde (« I-frame interval » = cadence) pour un retard précis.

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
