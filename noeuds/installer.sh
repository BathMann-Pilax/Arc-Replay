#!/usr/bin/env bash
# Installation d'un nœud Arc Replay sur Raspberry Pi OS (Bookworm ou plus récent).
#
#   sudo ./installer.sh camera <id> [serveur]   # Pi Zero 2 W / Pi 4 avec caméra CSI
#   sudo ./installer.sh cible [serveur]         # Pi 4 du coffre de cible
#
# <id> doit correspondre à une caméra de type « reseau » dans config/arc-replay.yml.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "À lancer avec sudo." >&2
  exit 1
fi

ROLE=${1:-}
ICI=$(cd "$(dirname "$0")" && pwd)
DEST=/opt/arc-replay

case "$ROLE" in
  camera)
    ID=${2:?"identifiant de caméra manquant (ex. : dessus)"}
    SERVEUR=${3:-10.42.0.1}
    ;;
  cible)
    SERVEUR=${2:-10.42.0.1}
    ;;
  *)
    echo "Usage : sudo $0 camera <id> [serveur] | cible [serveur]" >&2
    exit 1
    ;;
esac

echo "==> Paquets"
apt-get update -qq
apt-get install -y -qq python3-picamera2 ffmpeg chrony python3-yaml
if [[ $ROLE == cible ]]; then
  apt-get install -y -qq python3-opencv python3-numpy python3-websockets
fi

echo "==> Utilisateur de service"
id arc &>/dev/null || useradd --system --groups video --home-dir "$DEST" --shell /usr/sbin/nologin arc

echo "==> Fichiers"
install -d "$DEST/camera"
install -m 755 "$ICI/camera/streamer.py" "$DEST/camera/"
install -m 644 "$ICI/camera/recadrage.py" "$DEST/camera/"

echo "==> Heure : synchronisation sur le serveur (pas d'internet sur le terrain)"
cat > /etc/chrony/conf.d/arc-replay.conf <<EOF
server $SERVEUR iburst minpoll 4 maxpoll 6
makestep 1 -1
EOF
systemctl restart chrony

if [[ $ROLE == camera ]]; then
  cat > /etc/default/arc-replay-camera <<EOF
ARC_SERVEUR=$SERVEUR
ARC_CHEMIN=$ID
ARC_LARGEUR=1920
ARC_HAUTEUR=1080
ARC_FPS=30
ARC_DEBIT=6000000
# Caméra de cible sur le pas de tir (caméra HQ + objectif 25 mm) :
#   ARC_LARGEUR=1280 ARC_HAUTEUR=720 ARC_FPS=10
#   ARC_OPTIONS="--recadrage --capteur-complet"
ARC_OPTIONS=
EOF
  install -m 644 "$ICI/systemd/arc-replay-camera.service" /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable --now arc-replay-camera
  echo "Nœud caméra « $ID » installé. Réglages : /etc/default/arc-replay-camera"
else
  install -d "$DEST/cible"
  install -m 755 "$ICI/cible/cible.py" "$ICI/cible/calibrer.py" "$DEST/cible/"
  install -m 644 "$ICI/cible/detection.py" "$DEST/cible/"
  install -m 644 "$ICI/camera/streamer.py" "$ICI/camera/recadrage.py" "$DEST/cible/"
  if [[ ! -f $DEST/cible/cible.yml ]]; then
    sed "s/^serveur: .*/serveur: $SERVEUR          # adresse du serveur/" "$ICI/cible/cible.yml" > "$DEST/cible/cible.yml"
  fi
  chown -R arc "$DEST/cible"
  install -m 644 "$ICI/systemd/arc-replay-cible.service" /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable arc-replay-cible
  echo
  echo "Nœud cible installé. Avant de le démarrer, calibrez-le :"
  echo "  cd $DEST/cible && sudo -u arc python3 calibrer.py capture --sortie blason.jpg"
  echo "  (voir docs/noeud-cible.md), puis : sudo systemctl start arc-replay-cible"
fi
