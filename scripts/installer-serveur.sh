#!/usr/bin/env bash
# Préparation de l'hôte du serveur Arc Replay (Pi 5, mini-PC Debian/Ubuntu…).
#
#   sudo ./scripts/installer-serveur.sh            # USB + heure
#   sudo ./scripts/installer-serveur.sh --wifi     # + point d'accès Wi-Fi « ArcReplay »
#
# Ce script ne touche pas à Docker : installez-le avant (https://docs.docker.com/engine/install/).
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "À lancer avec sudo." >&2
  exit 1
fi
ICI=$(cd "$(dirname "$0")" && pwd)

command -v docker >/dev/null || echo "Attention : Docker n'est pas installé."

echo "==> Clé USB : montage automatique dans /media/arc-usb"
apt-get install -y -qq exfatprogs >/dev/null || true
install -m 644 "$ICI/usb/99-arc-replay-usb.rules" /etc/udev/rules.d/
udevadm control --reload-rules

echo "==> Heure : ce serveur devient la référence du réseau local"
apt-get install -y -qq chrony >/dev/null
install -m 644 "$ICI/chrony-serveur.conf" /etc/chrony/conf.d/arc-replay.conf
systemctl restart chrony

if [[ ${1:-} == --wifi ]]; then
  "$ICI/point-acces-wifi.sh"
fi

echo
echo "Hôte prêt. Ensuite : docker compose up -d   (depuis le dossier du projet)"
