#!/usr/bin/env bash
# Tests de faisabilité du profil « Pi 3 seul » (Raspberry Pi 3 B+, 1 Go) :
# caméra HQ (vue cible, encodeur matériel) + 3 Logitech C920 en H.264 (passthrough)
# + écran en kiosque (cage + Chromium) qui décode 4 vidéos.
#
#   sudo ./scripts/test-faisabilite-pi3.sh                 # tout (environ 6 minutes)
#   sudo ./scripts/test-faisabilite-pi3.sh --etape 4       # une seule étape (1 à 4)
#   sudo ./scripts/test-faisabilite-pi3.sh --installer     # installe d'abord les outils manquants
#   sudo ./scripts/test-faisabilite-pi3.sh --duree 30      # durée des captures (60 s par défaut)
#
# À lancer AVANT d'installer Arc Replay sur ce Pi, serveur Docker arrêté
# (sinon il occupe les caméras). Brancher les 3 C920 sur le hub USB alimenté
# et la HQ Camera sur le port CSI. Pour l'étape 4, la télé doit être branchée
# en HDMI : le test prend l'écran pendant environ 2 minutes.
#
# Rapport écrit dans ./rapport-faisabilite-pi3-<date>.txt (à transmettre).
# Les étapes 1 et 2 sont bloquantes : si elles échouent, le script s'arrête.
set -uo pipefail

ETAPE=""
DUREE=60
INSTALLER=0
while (( $# )); do
  case "$1" in
    --etape) ETAPE=$2; shift 2 ;;
    --duree) DUREE=$2; shift 2 ;;
    --installer) INSTALLER=1; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "Option inconnue : $1" >&2; exit 2 ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "À lancer avec sudo (dmesg, écran, réglages vidéo)." >&2
  exit 2
fi

ID_C920="046d:082d"
NB_C920=3
TRAVAIL=$(mktemp -d /var/tmp/arc-faisabilite.XXXXXX)
RAPPORT="$PWD/rapport-faisabilite-pi3-$(date +%Y%m%d-%H%M).txt"
UTILISATEUR=${SUDO_USER:-pi}
trap 'nettoyer' EXIT

nettoyer() {
  jobs -p | xargs -r kill 2>/dev/null
  systemctl stop arc-test-ecran.service 2>/dev/null
  rm -f /etc/pam.d/arc-test-ecran
  rm -rf "$TRAVAIL"
}

# --- affichage et rapport ------------------------------------------------------

exec > >(tee -a "$RAPPORT") 2>&1
VERT=$'\033[32m'; ROUGE=$'\033[31m'; JAUNE=$'\033[33m'; GRAS=$'\033[1m'; FIN=$'\033[0m'
ok()    { echo "  ${VERT}✔${FIN} $*"; }
ko()    { echo "  ${ROUGE}✘${FIN} $*"; }
alerte(){ echo "  ${JAUNE}!${FIN} $*"; }
info()  { echo "  · $*"; }
titre() { echo; echo "${GRAS}=== $* ===${FIN}"; }
verdict() { echo; echo "${GRAS}>>> VERDICT : $*${FIN}"; }

etape_demandee() { [[ -z $ETAPE || $ETAPE == "$1" ]]; }

# --- outils ------------------------------------------------------------------

PAQUETS=(v4l-utils ffmpeg usbutils python3 python3-websockets cage)
chromium_bin() { command -v chromium || command -v chromium-browser; }
rpicam_bin() { command -v rpicam-vid || command -v libcamera-vid; }

verifier_outils() {
  local manquants=()
  command -v v4l2-ctl >/dev/null || manquants+=(v4l-utils)
  command -v ffmpeg >/dev/null || manquants+=(ffmpeg)
  command -v lsusb >/dev/null || manquants+=(usbutils)
  rpicam_bin >/dev/null || manquants+=(rpicam-apps)
  if etape_demandee 4; then
    command -v cage >/dev/null || manquants+=(cage)
    chromium_bin >/dev/null || manquants+=(chromium)
    python3 -c "import websockets" 2>/dev/null || manquants+=(python3-websockets)
  fi
  if (( ${#manquants[@]} )); then
    if (( INSTALLER )); then
      apt-get update -qq
      # Le paquet s'appelle chromium (Bookworm et suivants) ou chromium-browser (anciennes versions)
      for p in "${manquants[@]}"; do
        apt-get install -y -qq "$p" >/dev/null 2>&1 \
          || { [[ $p == chromium ]] && apt-get install -y -qq chromium-browser >/dev/null 2>&1; } \
          || alerte "paquet $p introuvable"
      done
    else
      ko "outils manquants : ${manquants[*]}"
      echo "     Relancez avec --installer, ou : sudo apt install ${manquants[*]}"
      exit 2
    fi
  fi
}

# --- mesures système -----------------------------------------------------------

cpu_occupe() {  # pourcentage CPU occupé depuis l'appel précédent
  local a b c d e f g h total inactif
  read -r _ a b c d e f g h _ < /proc/stat
  total=$((a + b + c + d + e + f + g + h)); inactif=$((d + e))
  if [[ -n ${CPU_TOTAL:-} ]]; then
    local dt=$((total - CPU_TOTAL)) di=$((inactif - CPU_INACTIF))
    (( dt > 0 )) && echo $(( 100 * (dt - di) / dt )) || echo 0
  fi
  CPU_TOTAL=$total; CPU_INACTIF=$inactif
}
ram_libre_mo() { awk '/MemAvailable/ {print int($2 / 1024)}' /proc/meminfo; }
temperature() { vcgencmd measure_temp 2>/dev/null | grep -oE '[0-9.]+' || echo "?"; }
throttled() { vcgencmd get_throttled 2>/dev/null | cut -d= -f2 || echo "?"; }

expliquer_throttled() {
  local v=$(( ${1:-0} ))
  (( v == 0 )) && { ok "get_throttled = 0x0 (ni sous-tension, ni bridage)"; return 0; }
  ko "get_throttled = $1 :"
  (( v & 0x1 ))     && info "  sous-tension EN COURS"
  (( v & 0x2 ))     && info "  fréquence ARM plafonnée EN COURS"
  (( v & 0x4 ))     && info "  bridage EN COURS"
  (( v & 0x8 ))     && info "  limite de température EN COURS"
  (( v & 0x10000 )) && info "  sous-tension depuis le démarrage (alimentation insuffisante)"
  (( v & 0x40000 )) && info "  bridage depuis le démarrage"
  (( v & 0x80000 )) && info "  limite de température atteinte depuis le démarrage"
  return 1
}

# Échantillonne CPU / RAM / température pendant $1 secondes -> variables MAX_CPU, MOY_CPU, MIN_RAM, MAX_TEMP
surveiller() {
  local duree=$1 n=0 somme=0 c r t
  MAX_CPU=0; MIN_RAM=99999; MAX_TEMP=0
  cpu_occupe >/dev/null
  for ((s = 0; s < duree; s += 5)); do
    sleep 5
    c=$(cpu_occupe); r=$(ram_libre_mo); t=$(temperature)
    (( c > MAX_CPU )) && MAX_CPU=$c
    (( r < MIN_RAM )) && MIN_RAM=$r
    awk -v t="$t" -v m="$MAX_TEMP" 'BEGIN {exit !(t > m)}' && MAX_TEMP=$t
    somme=$((somme + c)); n=$((n + 1))
  done
  MOY_CPU=$(( n ? somme / n : 0 ))
}

# Lignes dmesg apparues depuis le repère
repere_dmesg() { REPERE_DMESG=$(dmesg | wc -l); }
nouveau_dmesg() { dmesg | tail -n +"$((REPERE_DMESG + 1))"; }

# --- caméras C920 ----------------------------------------------------------------

C920=()
trouver_c920() {
  C920=()
  local dev props
  for dev in /dev/video*; do
    props=$(udevadm info -q property -n "$dev" 2>/dev/null) || continue
    grep -q "^ID_VENDOR_ID=046d$" <<<"$props" || continue
    grep -q "^ID_MODEL_ID=082d$" <<<"$props" || continue
    # Une C920 crée deux nœuds : on garde celui qui capture la vidéo
    v4l2-ctl -d "$dev" --info 2>/dev/null | sed -n '/Device Caps/,$p' | grep -q "Video Capture" || continue
    C920+=("$dev")
  done
}

a_le_format() {  # $1 dev, $2 fourcc, $3 taille, $4 fps minimal
  v4l2-ctl -d "$1" --list-formats-ext 2>/dev/null | awk -v f="$2" -v t="$3" -v fps="$4" '
    /\[[0-9]+\]: '\''/ { split($0, a, "'\''"); fmt = a[2] }
    /Size: Discrete/   { taille = $3 }
    /Interval:/ {
      if (fmt == f && taille == t && match($0, /\([0-9.]+ fps\)/) && substr($0, RSTART + 1, RLENGTH - 6) + 0 >= fps) ok = 1
    }
    END { exit !ok }'
}

# =====================================================================================
titre "Arc Replay — faisabilité « Pi 3 seul » — $(date '+%d/%m/%Y %H:%M')"
info "Modèle : $(tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo inconnu)"
info "Système : $(. /etc/os-release; echo "$PRETTY_NAME") — noyau $(uname -r) — $(getconf LONG_BIT) bits"
info "RAM totale : $(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo) Mo — libre : $(ram_libre_mo) Mo — zram : $(swapon --show=NAME --noheadings 2>/dev/null | grep -c zram) périphérique(s)"
info "CMA : $(awk '/CmaTotal/ {print int($2/1024)}' /proc/meminfo) Mo — température $(temperature) °C — get_throttled $(throttled)"
if docker ps -q 2>/dev/null | grep -q .; then
  alerte "des conteneurs Docker tournent : arrêtez Arc Replay (docker compose down) pour un test propre"
fi
verifier_outils

# --- Étape 1 : H.264 sur chaque C920 -------------------------------------------------
if etape_demandee 1 || etape_demandee 2 || etape_demandee 3 || etape_demandee 4; then
  trouver_c920
fi

if etape_demandee 1; then
  titre "Étape 1 — Les C920 proposent-elles le H.264 ?"
  info "Caméras USB $ID_C920 vues par lsusb : $(lsusb -d "$ID_C920" | wc -l)"
  if lsusb | grep -qi "046d:08e5\|046d:0892\|046d:0893"; then
    alerte "une C920 récente est branchée (046d:08e5 / 0892 / 0893) : ces versions n'ont plus de H.264"
  fi
  avec_h264=0
  for dev in "${C920[@]}"; do
    chemin=$(udevadm info -q property -n "$dev" | sed -n 's/^ID_PATH=//p')
    if a_le_format "$dev" H264 1280x720 30; then
      ok "$dev ($chemin) : H.264 1280x720 à 30 i/s"
      avec_h264=$((avec_h264 + 1))
    elif v4l2-ctl -d "$dev" --list-formats-ext 2>/dev/null | grep -q "'H264'"; then
      alerte "$dev ($chemin) : H.264 présent, mais pas en 1280x720 à 30 i/s"
      avec_h264=$((avec_h264 + 1))
    else
      ko "$dev ($chemin) : pas de H.264 (formats : $(v4l2-ctl -d "$dev" --list-formats 2>/dev/null | grep -oE "'[A-Z0-9]+'" | tr '\n' ' '))"
    fi
  done
  if (( ${#C920[@]} < NB_C920 )); then
    ko "${#C920[@]} C920 ($ID_C920) trouvée(s) sur $NB_C920 attendues"
  fi
  if (( avec_h264 < NB_C920 )); then
    verdict "${ROUGE}Pi 3 impossible avec ces caméras${FIN} (il faut $NB_C920 C920 $ID_C920 avec H.264 : le Pi 3 ne peut pas encoder 3 flux)"
    exit 1
  fi
  verdict "${VERT}étape 1 réussie${FIN} : $avec_h264 C920 en H.264"
fi

# --- Étape 2 : 3 captures H.264 simultanées ---------------------------------------------

# Capture en parallèle ($1 = taille) pendant DUREE s ; enregistre les flux pour l'étape 4.
# Renvoie 0 si toutes les caméras tiennent ~30 i/s sans erreur USB.
capturer_ensemble() {
  local taille=$1 i=0 dev reussite=0 pids=()
  repere_dmesg
  for dev in "${C920[@]}"; do
    ffmpeg -hide_banner -nostdin -loglevel info -f v4l2 -input_format h264 -video_size "$taille" \
      -framerate 30 -i "$dev" -t "$DUREE" -c copy -y "$TRAVAIL/c920-$i.mp4" \
      > "$TRAVAIL/ffmpeg-$i.log" 2>&1 &
    pids+=($!)
    i=$((i + 1))
  done
  surveiller "$DUREE"
  for p in "${pids[@]}"; do wait "$p"; done
  i=0
  for dev in "${C920[@]}"; do
    local images ips erreurs
    images=$(ffprobe -v error -count_packets -select_streams v:0 -show_entries stream=nb_read_packets \
      -of csv=p=0 "$TRAVAIL/c920-$i.mp4" 2>/dev/null || echo 0)
    ips=$(awk -v n="${images:-0}" -v d="$DUREE" 'BEGIN {printf "%.1f", n / d}')
    erreurs=$(grep -ciE "error|No space left|Cannot allocate|Input/output" "$TRAVAIL/ffmpeg-$i.log")
    if awk -v i="$ips" 'BEGIN {exit !(i >= 27)}' && (( erreurs == 0 )); then
      ok "$dev : $images images en ${DUREE} s ($ips i/s), aucune erreur"
    else
      ko "$dev : $images images en ${DUREE} s ($ips i/s), $erreurs erreur(s) ffmpeg"
      grep -iE "error|No space|allocate" "$TRAVAIL/ffmpeg-$i.log" | head -3 | sed 's/^/       /'
      reussite=1
    fi
    i=$((i + 1))
  done
  local usb
  usb=$(nouveau_dmesg | grep -iE "No space left on device|not enough bandwidth|Failed to submit URB|uvcvideo.*(error|fail)|reset .* USB" )
  if [[ -n $usb ]]; then
    ko "messages USB dans dmesg :"
    sed 's/^/       /' <<<"$usb" | head -8
    reussite=1
  else
    ok "dmesg : aucune erreur USB (pas de « No space left on device »)"
  fi
  info "pendant la capture : CPU moyen $MOY_CPU % (max $MAX_CPU %), RAM libre min $MIN_RAM Mo, $MAX_TEMP °C max"
  return $reussite
}

TAILLE_C920=""
if etape_demandee 2; then
  titre "Étape 2 — 3 C920 ensemble en H.264 pendant $DUREE s (copie, sans transcodage)"
  if (( ${#C920[@]} < NB_C920 )); then
    verdict "${ROUGE}impossible : ${#C920[@]} C920 branchée(s) sur $NB_C920${FIN}"
    exit 1
  fi
  info "1280x720 à 30 i/s…"
  if capturer_ensemble 1280x720; then
    TAILLE_C920=1280x720
  else
    info "Nouvel essai en 640x480 à 30 i/s…"
    if capturer_ensemble 640x480; then
      TAILLE_C920=640x480
      alerte "le 720p ne passe pas à 3 caméras : profil Pi 3 en 640x480"
    fi
  fi
  if [[ -z $TAILLE_C920 ]]; then
    verdict "${ROUGE}Pi 3 impossible : les 3 C920 ne capturent pas ensemble${FIN} (bande passante USB du Pi 3 ; essayer 2 caméras)"
    exit 1
  fi
  verdict "${VERT}étape 2 réussie${FIN} : 3 C920 en $TAILLE_C920 à 30 i/s"
fi
TAILLE_C920=${TAILLE_C920:-1280x720}

# --- Étape 3 : + caméra HQ (encodeur matériel) ---------------------------------------------

if etape_demandee 3; then
  titre "Étape 3 — HQ Camera (encodeur matériel 1280x720 à 15 i/s) + 3 C920, $DUREE s"
  RPICAM=$(rpicam_bin)
  if ! "${RPICAM%-vid}-hello" --list-cameras 2>/dev/null | grep -qi "imx477"; then
    "${RPICAM%-vid}-hello" --list-cameras 2>&1 | sed 's/^/       /' | head -6
    alerte "HQ Camera (imx477) non détectée : nappe, ou camera_auto_detect=1 dans /boot/firmware/config.txt"
  fi
  "$RPICAM" -t $((DUREE * 1000)) -n --width 1280 --height 720 --framerate 15 --codec h264 \
    --intra 15 --inline -o "$TRAVAIL/hq.h264" > "$TRAVAIL/hq.log" 2>&1 &
  pid_hq=$!
  sleep 3
  if capturer_ensemble "$TAILLE_C920"; then ok "les C920 tiennent avec la HQ en plus"; else ko "les C920 décrochent avec la HQ en plus"; fi
  wait "$pid_hq"; code_hq=$?
  if (( code_hq == 0 )) && [[ -s $TRAVAIL/hq.h264 ]]; then
    ffmpeg -hide_banner -loglevel error -framerate 15 -i "$TRAVAIL/hq.h264" -c copy -y "$TRAVAIL/hq.mp4"
    images=$(ffprobe -v error -count_packets -select_streams v:0 -show_entries stream=nb_read_packets -of csv=p=0 "$TRAVAIL/hq.mp4")
    ips_hq=$(awk -v n="$images" -v d="$DUREE" 'BEGIN {printf "%.1f", n/d}')
    if awk -v i="$ips_hq" 'BEGIN {exit !(i >= 13)}'; then
      ok "HQ : $images images en $DUREE s ($ips_hq i/s), encodeur matériel"
    else
      ko "HQ : $images images en $DUREE s ($ips_hq i/s, 15 attendues) : encodeur matériel saturé ?"
    fi
  else
    ko "HQ : échec de $RPICAM (code $code_hq)"
    tail -5 "$TRAVAIL/hq.log" | sed 's/^/       /'
  fi
  echo
  info "Bilan de charge (4 caméras) :"
  (( MAX_CPU < 85 )) && ok "CPU : moyen $MOY_CPU %, max $MAX_CPU %" || alerte "CPU : moyen $MOY_CPU %, max $MAX_CPU % (peu de marge pour MediaMTX et Chromium)"
  if (( MIN_RAM >= 300 )); then ok "RAM libre minimale : $MIN_RAM Mo"
  elif (( MIN_RAM >= 150 )); then alerte "RAM libre minimale : $MIN_RAM Mo (juste)"
  else ko "RAM libre minimale : $MIN_RAM Mo (< 150 Mo : prévoir l'installation sans Docker)"; fi
  awk -v t="$MAX_TEMP" 'BEGIN {exit !(t < 75)}' && ok "température max : $MAX_TEMP °C" || alerte "température max : $MAX_TEMP °C (bridage à 80 °C)"
  expliquer_throttled "$(throttled)" || true
fi

# --- Étape 4 : décodage de 4 vidéos dans Chromium (cage) -----------------------------------

# Page de test : N vidéos en mosaïque, servie en local
preparer_page() {  # $1 = liste de fichiers vidéo
  local html="$TRAVAIL/page/index.html" f
  mkdir -p "$TRAVAIL/page"
  {
    echo '<!doctype html><meta charset="utf-8"><title>test</title>'
    echo '<style>html,body{margin:0;background:#000;height:100%}body{display:grid;grid-template-columns:1fr 1fr;gap:4px}video{width:100%;height:100%;object-fit:contain}</style>'
    for f in "$@"; do
      ln -sf "$f" "$TRAVAIL/page/$(basename "$f")"
      echo "<video src=\"$(basename "$f")\" muted autoplay loop playsinline></video>"
    done
  } > "$html"
}

# Client CDP : décodeur choisi par Chromium pour chaque vidéo, images décodées / perdues
cat > "$TRAVAIL/cdp.py" <<'PY'
import asyncio, json, sys, time, urllib.request
import websockets

async def principal(duree):
    pages = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
    url = next(p["webSocketDebuggerUrl"] for p in pages if p.get("type") == "page")
    decodeurs = {}
    async with websockets.connect(url, max_size=None) as ws:
        n = 0
        async def envoyer(methode, params=None):
            nonlocal n
            n += 1
            await ws.send(json.dumps({"id": n, "method": methode, "params": params or {}}))
            return n
        await envoyer("Media.enable")
        await envoyer("Page.reload")       # les lecteurs créés après Media.enable sont suivis
        fin = time.time() + duree
        while time.time() < fin:
            try:
                m = json.loads(await asyncio.wait_for(ws.recv(), 1))
            except asyncio.TimeoutError:
                continue
            if m.get("method") == "Media.playerPropertiesChanged":
                lecteur = m["params"]["playerId"]
                for p in m["params"]["properties"]:
                    if p["name"] in ("kVideoDecoderName", "kIsPlatformVideoDecoder"):
                        decodeurs.setdefault(lecteur, {})[p["name"]] = p["value"]
        num = await envoyer("Runtime.evaluate", {"returnByValue": True, "expression":
            "JSON.stringify([...document.querySelectorAll('video')].map(v => {"
            " const q = v.getVideoPlaybackQuality();"
            " return {fichier: v.src.split('/').pop(), decodees: q.totalVideoFrames,"
            " perdues: q.droppedVideoFrames, taille: v.videoWidth + 'x' + v.videoHeight}; }))"})
        while True:
            m = json.loads(await ws.recv())
            if m.get("id") == num:
                videos = json.loads(m["result"]["result"]["value"])
                break
    print(json.dumps({"decodeurs": list(decodeurs.values()), "videos": videos}))

asyncio.run(principal(float(sys.argv[1])))
PY

# Lance Chromium dans cage sur tty1 (comme le futur service arc-replay-ecran), $1 = options en plus
lancer_kiosque() {
  local chrome
  chrome=$(chromium_bin)
  chown -R "$UTILISATEUR" "$TRAVAIL" 2>/dev/null
  chmod 755 "$TRAVAIL"
  printf '%s\n' "auth required pam_unix.so nullok" "account required pam_unix.so" \
    "session required pam_unix.so" "session required pam_systemd.so" > /etc/pam.d/arc-test-ecran
  systemctl stop getty@tty1.service 2>/dev/null
  systemd-run --unit=arc-test-ecran --collect \
    -p User="$UTILISATEUR" -p PAMName=arc-test-ecran -p TTYPath=/dev/tty1 \
    -p StandardInput=tty-fail -p StandardOutput=journal -p StandardError=journal \
    -p UtmpIdentifier=tty1 -p UtmpMode=user -p TTYReset=yes -p TTYVHangup=yes \
    /usr/bin/cage -s -- "$chrome" --kiosk --noerrdialogs --disable-infobars \
    --autoplay-policy=no-user-gesture-required --renderer-process-limit=1 \
    --disk-cache-size=1 --disable-extensions --user-data-dir="$TRAVAIL/profil" \
    --remote-debugging-port=9222 "$@" "http://127.0.0.1:8765/index.html" >/dev/null
  for _ in $(seq 1 40); do
    python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9222/json/list', timeout=1)" \
      2>/dev/null && return 0
    sleep 1
  done
  return 1
}

arreter_kiosque() {
  systemctl stop arc-test-ecran.service 2>/dev/null
  sleep 2
}

# Un essai : $1 = libellé, $2 = nombre de vidéos, reste = options Chromium
ESSAI_OK=1
essai_decodage() {
  local libelle=$1 nb=$2; shift 2
  local videos=("${FICHIERS_TEST[@]:0:$nb}") sortie
  preparer_page "${videos[@]}"
  info "$libelle : $nb vidéo(s) $*"
  if ! lancer_kiosque "$@"; then
    ko "Chromium n'a pas démarré dans cage (journalctl -u arc-test-ecran)"
    journalctl -u arc-test-ecran --no-pager -n 8 | sed 's/^/       /'
    arreter_kiosque; ESSAI_OK=1; return
  fi
  CPU_TOTAL=""; cpu_occupe >/dev/null
  sortie=$(python3 "$TRAVAIL/cdp.py" 40 2>&1)
  local cpu ram; cpu=$(cpu_occupe); ram=$(ram_libre_mo)
  arreter_kiosque
  python3 - "$sortie" "$cpu" "$ram" <<'PY'
import json, sys
try:
    d = json.loads(sys.argv[1].strip().splitlines()[-1])
except Exception:
    print("  ✘ mesure impossible :", sys.argv[1][-300:]); sys.exit(1)
mat = [x for x in d["decodeurs"] if x.get("kIsPlatformVideoDecoder") is True]
noms = sorted({x.get("kVideoDecoderName", "?") for x in d["decodeurs"]})
print(f"    décodeur(s) : {', '.join(noms) or 'inconnu'} — matériel pour {len(mat)}/{len(d['videos'])} vidéo(s)")
pire = 0
for v in d["videos"]:
    taux = 100 * v["perdues"] / max(1, v["decodees"])
    pire = max(pire, taux)
    print(f"    {v['fichier']:<12} {v['taille']:<9} {v['decodees']:>5} images, {v['perdues']:>4} perdues ({taux:.1f} %)")
print(f"    CPU {sys.argv[2]} %, RAM libre {sys.argv[3]} Mo")
materiel = len(mat) == len(d["videos"]) and len(d["videos"]) > 0
sys.exit(0 if materiel and pire < 5 else 3 if materiel else 2)
PY
  ESSAI_OK=$?
}

if etape_demandee 4 && ! id "$UTILISATEUR" >/dev/null 2>&1; then
  ko "utilisateur « $UTILISATEUR » introuvable pour lancer l'écran : lancez le script avec sudo depuis votre compte"
  exit 2
fi
if etape_demandee 4; then
  titre "Étape 4 — Décodage dans Chromium en kiosque (cage), l'écran est utilisé ~2 min"
  FICHIERS_TEST=()
  for i in 0 1 2; do [[ -s $TRAVAIL/c920-$i.mp4 ]] && FICHIERS_TEST+=("$TRAVAIL/c920-$i.mp4"); done
  [[ -s $TRAVAIL/hq.mp4 ]] && FICHIERS_TEST=("$TRAVAIL/hq.mp4" "${FICHIERS_TEST[@]}")
  if (( ${#FICHIERS_TEST[@]} < 4 )); then
    info "Vidéos de test manquantes (étapes 2 et 3 non lancées) : capture de 30 s…"
    DUREE=30 capturer_ensemble "$TAILLE_C920" >/dev/null
    FICHIERS_TEST=("$TRAVAIL"/c920-*.mp4)
    while (( ${#FICHIERS_TEST[@]} < 4 )); do FICHIERS_TEST+=("${FICHIERS_TEST[0]}"); done
  fi
  ( cd "$TRAVAIL/page" 2>/dev/null || mkdir -p "$TRAVAIL/page" && cd "$TRAVAIL/page" && \
    exec python3 -m http.server 8765 --bind 127.0.0.1 ) >/dev/null 2>&1 &
  sleep 1

  essai_decodage "Essai A (réglages par défaut)" 4
  resultat=$ESSAI_OK
  if (( resultat == 2 )); then
    # Décodeur logiciel : on tente l'accélération V4L2 de Chromium
    essai_decodage "Essai B (accélération V4L2 forcée)" 4 \
      --enable-features=AcceleratedVideoDecodeLinuxGL,AcceleratedVideoDecodeLinuxZeroCopyGL,VaapiVideoDecoder \
      --ignore-gpu-blocklist --use-gl=egl
    resultat=$ESSAI_OK
    OPTIONS_HW="--enable-features=AcceleratedVideoDecodeLinuxGL,AcceleratedVideoDecodeLinuxZeroCopyGL --ignore-gpu-blocklist --use-gl=egl"
  else
    OPTIONS_HW=""
  fi
  if (( resultat == 0 )); then
    verdict "${VERT}étape 4 réussie${FIN} : 4 vues décodées en matériel, moins de 5 % d'images perdues${OPTIONS_HW:+ (options : $OPTIONS_HW)}"
  else
    alerte "4 vues : décodage logiciel ou trop d'images perdues — repli « 2 vues affichées » (2 archer + cible)"
    # shellcheck disable=SC2086
    essai_decodage "Essai C (repli : 3 vidéos)" 3 $OPTIONS_HW
    if (( ESSAI_OK == 0 )); then
      verdict "${JAUNE}étape 4 en repli${FIN} : vues_affichees: 2 (la 3e vue archer reste enregistrée, affichable à la demande)"
    elif (( ESSAI_OK == 3 )); then
      verdict "${JAUNE}étape 4 limite${FIN} : décodage matériel mais images perdues même à 3 vues — baisser les C920 en 640x480"
    else
      verdict "${ROUGE}étape 4 échouée${FIN} : Chromium décode en logiciel ; l'écran du Pi 3 ne suivra pas plusieurs vues"
    fi
  fi
  systemctl start getty@tty1.service 2>/dev/null
fi

titre "Fin des tests"
info "Rapport : $RAPPORT"
info "Relancer une étape : sudo $0 --etape N"
