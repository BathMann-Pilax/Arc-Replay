#!/usr/bin/env bash
# Transforme le serveur en point d'accès Wi-Fi 5 GHz (NetworkManager).
# Le serveur prend l'adresse 10.42.0.1 et distribue les adresses (DHCP).
#
#   sudo SSID=ArcReplay MOT_DE_PASSE=changez-moi ./scripts/point-acces-wifi.sh
set -euo pipefail

SSID=${SSID:-ArcReplay}
MOT_DE_PASSE=${MOT_DE_PASSE:-arcreplay2026}
INTERFACE=${INTERFACE:-wlan0}
PAYS=${PAYS:-FR}

if (( ${#MOT_DE_PASSE} < 8 )); then
  echo "Le mot de passe doit faire au moins 8 caractères." >&2
  exit 1
fi

# Le pays règle les canaux 5 GHz autorisés
command -v raspi-config >/dev/null && raspi-config nonint do_wifi_country "$PAYS" || true

nmcli connection delete arc-replay-ap 2>/dev/null || true
nmcli connection add type wifi ifname "$INTERFACE" con-name arc-replay-ap autoconnect yes \
  ssid "$SSID" mode ap \
  802-11-wireless.band a 802-11-wireless.channel 36 \
  wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$MOT_DE_PASSE" \
  ipv4.method shared ipv4.addresses 10.42.0.1/24 ipv6.method disabled
nmcli connection up arc-replay-ap

echo "Point d'accès « $SSID » actif. Serveur : http://10.42.0.1/"
