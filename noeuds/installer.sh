#!/usr/bin/env bash
# Installation d'un nœud Arc Replay sur Raspberry Pi OS (Bookworm ou plus récent).
#
#   sudo ./installer.sh camera <id> [serveur]     # Pi Zero 2 W / Pi 4 avec caméra CSI
#   sudo ./installer.sh cible-directe [serveur]   # vue cible en direct, cadrée depuis la télécommande
#                                                 # (sans OpenCV : convient au Pi 3 B+ qui fait aussi serveur)
#   sudo ./installer.sh cible [serveur]           # nœud cible avec détection d'impact (OpenCV)
#
# <id> doit correspondre à une caméra de type « reseau » dans config/arc-replay.yml.
# Serveur et nœud sur le même Pi : serveur 127.0.0.1 (l'heure n'est alors pas
# synchronisée sur un autre serveur : c'est déjà la même horloge).
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
  cible | cible-directe)
    SERVEUR=${2:-10.42.0.1}
    ;;
  *)
    echo "Usage : sudo $0 camera <id> [serveur] | cible-directe [serveur] | cible [serveur]" >&2
    exit 1
    ;;
esac

# Adresse locale : serveur sur ce même Pi
case "${SERVEUR%%:*}" in
  127.0.0.1 | localhost | ::1) LOCAL=1 ;;
  *) LOCAL=0 ;;
esac

echo "==> Paquets"
apt-get update -qq
# python3-websockets : canal de commande avec le serveur (cadrage depuis la télécommande)
apt-get install -y -qq python3-picamera2 ffmpeg python3-yaml python3-websockets
(( LOCAL )) || apt-get install -y -qq chrony
if [[ $ROLE == cible ]]; then
  apt-get install -y -qq python3-opencv python3-numpy
fi

echo "==> Utilisateur de service"
id arc &>/dev/null || useradd --system --groups video --home-dir "$DEST" --shell /usr/sbin/nologin arc

echo "==> Fichiers"
FICHIERS_CAMERA=("$ICI"/camera/{streamer,cadrage,canal,vue_cadree}.py)
install -d "$DEST/camera"
install -m 644 "${FICHIERS_CAMERA[@]}" "$DEST/camera/"
chmod 755 "$DEST/camera/streamer.py"
# Cadrage enregistré, restauré au démarrage (StateDirectory des services)
install -d -o arc -m 755 /var/lib/arc-replay

if (( LOCAL )); then
  echo "==> Heure : serveur sur ce Pi, pas de synchronisation à régler"
  # Surtout ne pas écrire /etc/chrony/conf.d/arc-replay.conf : c'est la
  # configuration de serveur d'heure posée par scripts/installer-serveur.sh.
else
  echo "==> Heure : synchronisation sur le serveur (pas d'internet sur le terrain)"
  cat > /etc/chrony/conf.d/arc-replay.conf <<EOF
server ${SERVEUR%%:*} iburst minpoll 4 maxpoll 6
makestep 1 -1
EOF
  systemctl restart chrony
fi

if [[ $ROLE == camera ]]; then
  cat > /etc/default/arc-replay-camera <<EOF
ARC_SERVEUR=$SERVEUR
ARC_CHEMIN=$ID
ARC_LARGEUR=1920
ARC_HAUTEUR=1080
ARC_FPS=30
ARC_DEBIT=6000000
# Caméra cadrée depuis la télécommande (réglages du flux lus dans config/arc-replay.yml) :
#   ARC_OPTIONS="--recadrage"
ARC_OPTIONS=
EOF
  install -m 644 "$ICI/systemd/arc-replay-camera.service" /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable --now arc-replay-camera
  echo "Nœud caméra « $ID » installé. Réglages : /etc/default/arc-replay-camera"
  exit 0
fi

# --- nœud cible (avec ou sans détection) ---------------------------------------
install -d "$DEST/cible"
install -m 755 "$ICI/cible/cible.py" "$DEST/cible/"
install -m 644 "${FICHIERS_CAMERA[@]}" "$DEST/cible/"
if [[ $ROLE == cible ]]; then
  install -m 755 "$ICI/cible/calibrer.py" "$DEST/cible/"
  install -m 644 "$ICI/cible/detection.py" "$DEST/cible/"
fi
if [[ ! -f $DEST/cible/cible.yml ]]; then
  DETECTION=$([[ $ROLE == cible ]] && echo true || echo false)
  sed -e "s/^serveur: .*/serveur: $SERVEUR          # adresse du serveur/" \
      -e "s/^detection: .*/detection: $DETECTION/" \
      "$ICI/cible/cible.yml" > "$DEST/cible/cible.yml"
fi
chown -R arc "$DEST/cible"
install -m 644 "$ICI/systemd/arc-replay-cible.service" /etc/systemd/system/
systemctl daemon-reload

if [[ $ROLE == cible-directe ]]; then
  systemctl enable --now arc-replay-cible
  echo
  echo "Vue cible en direct installée. Cadrage : télécommande, section « Caméra cible »."
  echo "Réglages du flux : caméra « cible » dans config/arc-replay.yml (direct: true)."
  echo "Journal : journalctl -u arc-replay-cible -f"
else
  systemctl enable arc-replay-cible
  echo
  echo "Nœud cible installé. Avant de le démarrer, calibrez-le :"
  echo "  cd $DEST/cible && sudo -u arc python3 calibrer.py capture --sortie blason.jpg"
  echo "  (voir docs/noeud-cible.md), puis : sudo systemctl start arc-replay-cible"
fi
