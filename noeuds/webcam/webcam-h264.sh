#!/bin/sh
# Webcam USB à H.264 intégré (Logitech C920 d'origine…) publiée vers le serveur.
#
# Avec ffmpeg, la C920 n'envoie une image clé que toutes les 10 s : trop peu
# pour le différé et la découpe des clips. GStreamer (uvch264src) sait régler
# cet intervalle par l'extension H.264 de la caméra : une image clé par seconde,
# sans réencodage, donc presque sans calcul pour le serveur.
#
# Réglages : /etc/default/arc-replay-webcam-<id> (voir noeuds/installer.sh).
set -eu

: "${ARC_PERIPHERIQUE:?chemin de la webcam manquant}"
: "${ARC_CHEMIN:?identifiant de la caméra manquant}"
ARC_SERVEUR=${ARC_SERVEUR:-127.0.0.1}
ARC_LARGEUR=${ARC_LARGEUR:-1280}
ARC_HAUTEUR=${ARC_HAUTEUR:-720}
ARC_FPS=${ARC_FPS:-30}
ARC_DEBIT=${ARC_DEBIT:-2500000}
ARC_SECTEUR_HZ=${ARC_SECTEUR_HZ:-50}

# Anti-scintillement sous les néons (réglage perdu au débranchement : on le
# remet à chaque démarrage du service). 1 = 50 Hz, 2 = 60 Hz.
case $ARC_SECTEUR_HZ in
  60) frequence=2 ;;
  *) frequence=1 ;;
esac
v4l2-ctl -d "$ARC_PERIPHERIQUE" -c power_line_frequency=$frequence 2>/dev/null || true

exec gst-launch-1.0 -e \
  uvch264src device="$ARC_PERIPHERIQUE" name=src auto-start=true \
    iframe-period=1000 average-bitrate="$ARC_DEBIT" peak-bitrate="$ARC_DEBIT" \
  src.vidsrc ! "video/x-h264,width=$ARC_LARGEUR,height=$ARC_HAUTEUR,framerate=$ARC_FPS/1" \
  ! h264parse config-interval=-1 \
  ! rtspclientsink location="rtsp://$ARC_SERVEUR:8554/$ARC_CHEMIN" protocols=tcp
