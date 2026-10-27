#!/usr/bin/env bash
# Vérifie qu'une webcam USB convient à Arc Replay, avant d'en acheter d'autres.
#
#   ./scripts/tester-webcam.sh            # toutes les webcams branchées
#   ./scripts/tester-webcam.sh /dev/video2
#
# Pour chaque webcam : formats utiles (MJPEG 720p/1080p à 30 i/s), réglages
# importants pour le tir à l'arc (mise au point, 50 Hz, exposition) et le
# chemin à mettre dans config/arc-replay.yml.
# Nécessite v4l-utils : sudo apt install v4l-utils
set -uo pipefail

if ! command -v v4l2-ctl >/dev/null; then
  echo "v4l2-ctl introuvable : sudo apt install v4l-utils" >&2
  exit 1
fi

V4L_DIR=${V4L_DIR:-/dev/v4l}   # remplaçable pour les tests

ok()   { printf '  \033[32m✔\033[0m %s\n' "$*"; }
non()  { printf '  \033[31m✘\033[0m %s\n' "$*"; }
info() { printf '  · %s\n' "$*"; }

# Lien symbolique de $2 (by-id ou by-path) qui pointe vers le périphérique $1
lien_vers() {
  local cible lien
  cible=$(readlink -f "$1")
  for lien in "$V4L_DIR/$2"/*; do
    [[ -e $lien ]] || continue
    if [[ $(readlink -f "$lien") == "$cible" ]]; then
      echo "$lien"
      return
    fi
  done
}

# Formats capturables à ~30 i/s ou plus : « MJPG 1280x720 » par ligne
formats_30ips() {
  v4l2-ctl -d "$1" --list-formats-ext 2>/dev/null | awk '
    /\[[0-9]+\]: '\''/ { split($0, a, "'\''"); fmt = a[2] }
    /Size: Discrete/   { taille = $3 }
    /Interval:/ {
      # « (30.000 fps) » : portable mawk/gawk (Raspberry Pi OS utilise mawk)
      if (match($0, /\([0-9.]+ fps\)/) && substr($0, RSTART + 1, RLENGTH - 6) + 0 >= 29.9) print fmt, taille
    }' | sort -u
}

tester() {
  local dev=$1 nom pilote formats ctrls par_id par_path verdict=0
  pilote=$(v4l2-ctl -d "$dev" --info 2>/dev/null | awk -F': ' '/Driver name/ {print $2; exit}')
  [[ $pilote == uvcvideo ]] || return 1
  # Une webcam crée aussi un nœud « métadonnées » : on ne garde que la capture vidéo
  v4l2-ctl -d "$dev" --info 2>/dev/null | sed -n '/Device Caps/,$p' | grep -q "Video Capture" || return 1

  nom=$(v4l2-ctl -d "$dev" --info 2>/dev/null | awk -F': ' '/Card type/ {print $2; exit}')
  echo
  echo "=== $dev : ${nom:-webcam} ==="

  formats=$(formats_30ips "$dev")
  echo " Formats à 30 i/s"
  if grep -q "^MJPG 1280x720$" <<<"$formats"; then ok "MJPEG 1280x720 (720p)"; else non "pas de MJPEG 720p à 30 i/s"; verdict=1; fi
  if grep -q "^MJPG 1920x1080$" <<<"$formats"; then ok "MJPEG 1920x1080 (1080p)"; else info "pas de MJPEG 1080p à 30 i/s (720p suffit)"; fi
  if grep -q "^H264 " <<<"$formats"; then ok "H.264 intégré : encodeur: copy possible, soulage le serveur"; fi
  if grep -qE "^MJPG [0-9]+x[0-9]+$" <<<"$formats"; then
    info "MJPEG : $(grep '^MJPG' <<<"$formats" | cut -d' ' -f2 | sort -t x -k1,1nr | head -5 | tr '\n' ' ')"
  fi

  ctrls=$(v4l2-ctl -d "$dev" --list-ctrls 2>/dev/null)
  echo " Réglages"
  if grep -qE "^\s*(focus_automatic_continuous|focus_auto) " <<<"$ctrls"; then
    ok "autofocus désactivable (évite que la netteté saute de l'archer à l'arc)"
  elif grep -qE "^\s*focus_absolute " <<<"$ctrls"; then
    ok "mise au point manuelle"
  else
    info "mise au point fixe : pas de réglage, mais pas d'autofocus qui « cherche » non plus"
  fi
  if grep -qE "^\s*power_line_frequency " <<<"$ctrls"; then
    ok "anti-scintillement 50 Hz réglable (néons en salle)"
  else
    non "pas de réglage 50 Hz : risque de scintillement sous les néons"
    verdict=1
  fi
  if grep -qE "^\s*(auto_exposure|exposure_auto) " <<<"$ctrls"; then
    ok "exposition réglable"
  else
    info "exposition automatique seulement"
  fi

  echo " Configuration (config/arc-replay.yml)"
  par_path=$(lien_vers "$dev" by-path)
  par_id=$(lien_vers "$dev" by-id)
  if [[ -n $par_id ]]; then
    info "peripherique: $par_id"
  else
    non "pas de nom by-id : sans numéro de série, deux webcams identiques se confondent"
  fi
  if [[ -n $par_path ]]; then
    info "${par_id:+ou, }lié au port USB : peripherique: $par_path"
    info "  (à préférer pour plusieurs webcams identiques : toujours le même port pour la même vue)"
  fi

  echo " Verdict"
  if (( verdict == 0 )); then ok "convient à Arc Replay"; else non "à éviter, ou à réserver à une vue secondaire"; fi
  return 0
}

if (( $# )); then
  peripheriques=("$@")
else
  peripheriques=(/dev/video*)
fi

trouve=0
for dev in "${peripheriques[@]}"; do
  [[ -e $dev ]] || continue
  tester "$dev" && trouve=1
done

if (( ! trouve )); then
  echo "Aucune webcam USB trouvée. Branchez-la puis relancez (lsusb doit la lister)." >&2
  exit 1
fi

echo
echo "Réglages appliqués à la main (perdus au débranchement), par exemple :"
echo "  v4l2-ctl -d /dev/video0 -c power_line_frequency=1   # 50 Hz"
echo "  v4l2-ctl -d /dev/video0 -c focus_automatic_continuous=0 -c focus_absolute=0"
