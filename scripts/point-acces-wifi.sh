#!/usr/bin/env bash
# Transforme le serveur en point d'accès Wi-Fi 5 GHz (NetworkManager).
# Le serveur prend l'adresse 10.42.0.1 et distribue les adresses (DHCP).
# Le nom et le mot de passe sont recopiés dans config/arc-replay.yml : l'écran
# affiche alors un QR code pour se connecter au Wi-Fi.
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

# QR code Wi-Fi de l'écran : on recopie le nom et le mot de passe dans la configuration
CONFIG=${CONFIG:-$(cd "$(dirname "$0")/.." && pwd)/config/arc-replay.yml}
if [[ -f $CONFIG ]]; then
  SSID="$SSID" MOT_DE_PASSE="$MOT_DE_PASSE" python3 - "$CONFIG" <<'PY'
import os, re, sys
chemin = sys.argv[1]
texte = open(chemin, encoding="utf-8").read()
def yaml(v):  # chaîne YAML entre apostrophes
    return "'" + v.replace("'", "''") + "'"
for cle, val in (("wifi_ssid", os.environ["SSID"]), ("wifi_mot_de_passe", os.environ["MOT_DE_PASSE"])):
    ligne = f"  {cle}: {yaml(val)}"
    motif = re.compile(rf"^\s*#?\s*{cle}:.*$", re.M)
    if motif.search(texte):
        texte = motif.sub(lambda m: ligne, texte, count=1)
    else:
        texte = re.sub(r"^serveur:\s*$", lambda m: m.group(0) + "\n" + ligne, texte, count=1, flags=re.M)
open(chemin, "w", encoding="utf-8").write(texte)
PY
  echo "QR code Wi-Fi : nom et mot de passe enregistrés dans $CONFIG (rechargez la configuration)."
fi

echo "Point d'accès « $SSID » actif. Serveur : http://10.42.0.1/"
