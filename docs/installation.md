# Installation

## Matériel de référence

| Élément | Conseillé | Remarques |
|---|---|---|
| Serveur | Raspberry Pi 5 (4 ou 8 Go) + SSD NVMe | Ou mini-PC Intel N100, plus à l'aise au-delà de 3 caméras USB et pour le 100 i/s. Évitez la carte SD : l'enregistrement continu l'use vite. |
| Caméras autour de l'archer | Webcams USB UVC, MJPEG 720p ou 1080p | Une caméra qui sort du H.264 soulage le serveur (`encodeur: copy`). |
| Caméra ralenti | Webcam USB 100/120 i/s en 720p | 100 i/s en salle (éclairage 50 Hz), 120 i/s en extérieur. |
| Nœud cible | Raspberry Pi 4 + Camera Module 3 Wide | Dans le coffre d'éclairage, sur secteur. Pi 4 pour le Wi-Fi 5 GHz et le calcul. |
| Nœud caméra Wi-Fi | Pi Zero 2 W + Camera Module 3 | Pour une vue éloignée sans câble. |
| Micro (optionnel) | Micro USB | Détection automatique du lâcher. |
| Écran | TV + boîtier HDMI, ou tablette | Voir « Écran » plus bas. |

## 1. Serveur

### Système et Docker

Installez Raspberry Pi OS **64 bits** (Bookworm ou plus récent) ou Debian/Ubuntu, puis Docker :

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER   # puis se déconnecter / reconnecter
```

### Préparation de l'hôte

```bash
git clone https://github.com/<votre-compte>/arc-replay.git
cd arc-replay
sudo ./scripts/installer-serveur.sh --wifi
```

Le script :

- installe la règle udev qui monte automatiquement une clé USB dans `/media/arc-usb` ;
- fait du serveur la référence d'heure du réseau (chrony), pour les nœuds Pi ;
- avec `--wifi`, crée le point d'accès 5 GHz `ArcReplay` (adresse du serveur : `10.42.0.1`).

Nom et mot de passe du Wi-Fi :

```bash
sudo SSID=ClubArc MOT_DE_PASSE=un-vrai-mot-de-passe ./scripts/point-acces-wifi.sh
```

> Si le serveur est relié en Ethernet au réseau du club, le point d'accès n'est pas obligatoire : utilisez simplement l'adresse IP du serveur sur ce réseau, et passez-la aux nœuds (`installer.sh … <adresse>`).

### Caméras USB

Branchez les caméras, puis repérez leur identifiant stable :

```bash
ls -l /dev/v4l/by-id/
# usb-046d_HD_Pro_Webcam_C920_A1B2C3D4-video-index0 -> ../../video0
```

Utilisez toujours le chemin `by-id` (et l'entrée `-video-index0`) : `/dev/video0` peut changer de numéro au redémarrage.

Formats proposés par une caméra :

```bash
sudo apt install v4l-utils
v4l2-ctl -d /dev/v4l/by-id/usb-…-video-index0 --list-formats-ext
```

Cherchez une ligne `MJPG` (ou `H264`) avec la résolution et la cadence voulues, et reportez-les dans `config/arc-replay.yml` (voir [configuration.md](configuration.md)).

Conseils de câblage :

- répartissez les caméras sur les deux ports USB 3 du Pi 5 (contrôleurs séparés) ;
- rallonges : 5 m maximum en USB 2.0 passif. Au-delà, rallonge active avec hub alimenté, ou extendeur USB sur câble RJ45.

### Clé USB

Formatez-la en **exFAT** (lisible sur Windows, macOS, Android, iPad). Elle est montée automatiquement à l'insertion ; l'export se lance depuis la télécommande.

### Lancement

```bash
docker compose up -d --build
docker compose logs -f backend      # vérifier que les caméras sont configurées
```

Avec le micro de détection du lâcher :

```bash
docker compose --profile audio up -d --build
```

Réglage du seuil du micro : lancez le détecteur en mode réglage, tirez quelques flèches, et choisissez un seuil un peu sous le niveau des lâchers et nettement au-dessus du bruit ambiant.

```bash
docker compose run --rm -e MODE_REGLAGE=1 detecteur-lacher
# puis SEUIL_DB=-18 dans .env
```

### Images précompilées

Le workflow GitHub Actions publie des images arm64 et amd64 sur GHCR à chaque envoi sur `main`. Pour les utiliser au lieu de compiler sur le Pi :

```bash
cp .env.exemple .env
# dans .env : ARC_REGISTRE=ghcr.io/<votre-compte-github>
docker compose pull && docker compose up -d
```

Rendez les paquets publics dans GitHub (Packages → Package settings) ou faites `docker login ghcr.io` sur le serveur.

## 2. Nœud cible (Pi 4)

Raspberry Pi OS Lite 64 bits, caméra branchée, connecté au Wi-Fi `ArcReplay`. Ajoutez d'abord la caméra côté serveur (elle est déjà dans l'exemple) :

```yaml
  - id: cible
    nom: Cible
    type: reseau
```

Puis sur le Pi :

```bash
git clone https://github.com/<votre-compte>/arc-replay.git
cd arc-replay/noeuds
sudo ./installer.sh cible 10.42.0.1
```

Calibrez ensuite la détection : voir [noeud-cible.md](noeud-cible.md).

Si vous pouvez tirer un câble jusqu'au coffre, un Pi 4 avec carte PoE et un câble Ethernet est plus fiable que le Wi-Fi : un seul câble pour le courant et le réseau.

## 3. Nœud caméra Wi-Fi (Pi Zero 2 W, Pi 4)

Déclarez la caméra côté serveur avec `type: reseau` et un `id` (par exemple `dessus`), puis sur le Pi :

```bash
sudo ./installer.sh camera dessus 10.42.0.1
```

Résolution, cadence et débit se règlent dans `/etc/default/arc-replay-camera`, puis :

```bash
sudo systemctl restart arc-replay-camera
journalctl -u arc-replay-camera -f
```

Un Pi Zero 2 W n'a que du Wi-Fi 2,4 GHz : gardez-le à moins d'une quinzaine de mètres du serveur, et limitez-le à 1080p 30 i/s autour de 4 à 6 Mbit/s.

## 4. Écran

| Écran | Mise en place |
|---|---|
| Tablette | Ouvrir `http://10.42.0.1/` (ou `/?controles` pour avoir les commandes sur la même tablette), puis « Ajouter à l'écran d'accueil » pour le plein écran. |
| TV + mini-PC ou Pi | Navigateur en mode kiosque, voir ci-dessous. |
| TV + boîtier Android TV | Navigateur Chrome ou application kiosque pointant sur `http://10.42.0.1/`. |
| TV connectée seule | Possible pour 1 à 2 vues ; au-delà, le navigateur intégré est souvent trop lent. |

Mode kiosque (Raspberry Pi OS avec bureau, ou Debian) :

```bash
chromium-browser --kiosk --noerrdialogs --disable-infobars \
  --autoplay-policy=no-user-gesture-required http://10.42.0.1/
```

Sur le serveur lui-même branché à la TV, remplacez l'adresse par `http://localhost/`. Un Pi 5 décode le H.264 sans accélération matérielle : comptez 2 à 3 vues 720p au maximum dans ce cas. Un mini-PC N100 en affiche bien davantage.

## Dépannage

| Symptôme | Piste |
|---|---|
| « Caméra hors ligne » sur une vue USB | `docker compose logs mediamtx` : périphérique introuvable, format ou cadence non proposés par la caméra. |
| Vue réseau hors ligne | `journalctl -u arc-replay-camera` sur le nœud ; vérifier le Wi-Fi et l'adresse du serveur. |
| Retard qui dérive ou vues décalées | Vérifier l'heure du serveur (`chronyc tracking`) et que chaque source émet une image clé par seconde. |
| Clips manquants (statut « partiel ») | `docker compose logs backend` ; la caméra était-elle en ligne au moment du tir ? |
| Clé USB non détectée | Formatée en exFAT ou FAT32 ? `ls /media/arc-usb` sur l'hôte. |
