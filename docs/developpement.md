# Développement

Tout peut tourner sur un PC, sans Docker ni caméra, avec un flux de test ffmpeg.

## Prérequis

- Python 3.11 ou plus récent, Node 20 ou plus récent, ffmpeg ;
- le binaire MediaMTX de votre plateforme : [releases MediaMTX](https://github.com/bluenviron/mediamtx/releases).

## Lancer la pile en local

```bash
# 1. MediaMTX, avec enregistrements dans ./tmp/rec
mkdir -p tmp/rec tmp/data tmp/usb
sed "s#/recordings/#$PWD/tmp/rec/#" mediamtx/mediamtx.yml > tmp/mediamtx.yml
./mediamtx tmp/mediamtx.yml

# 2. Une fausse caméra (mire avec horloge), dans un autre terminal
ffmpeg -re -f lavfi -i "testsrc2=size=1280x720:rate=30" \
  -c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p \
  -g 30 -keyint_min 30 -sc_threshold 0 -b:v 3M \
  -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/test

# 3. Le back-end
cat > tmp/arc.yml <<EOF
serveur:
  usb_chemin: $PWD/tmp/usb
  usb_verifier_montage: false
  mediamtx_api: http://127.0.0.1:9997
  mediamtx_playback: http://127.0.0.1:9996
  donnees: $PWD/tmp/data
cameras:
  - {id: test, nom: Test, type: reseau}
EOF
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
ARC_CONFIG=../tmp/arc.yml ARC_DONNEES=../tmp/data uvicorn app.main:app --port 8100 --reload

# 4. L'interface
cd frontend
npm install
ARC_BACKEND=http://localhost:8100 npm run dev
```

Ouvrez `http://localhost:5173/` (écran) et `http://localhost:5173/telecommande`.

Simuler un tir et un impact :

```bash
curl -X POST localhost:8100/api/lacher -H 'content-type: application/json' -d '{}'
curl -X POST localhost:8100/api/impact -H 'content-type: application/json' \
  -d '{"x_mm": 35, "y_mm": -20, "diametre_mm": 400}'
```

## Tests

```bash
cd backend && pip install pytest && pytest -q
cd noeuds/cible && pip install opencv-python-headless numpy pyyaml pytest && pytest -q
cd detecteur-lacher && pip install numpy pytest && pytest -q
cd frontend && npm run build
```

La CI GitHub Actions lance ces mêmes tests, puis construit et publie les images Docker arm64/amd64.

## API du back-end

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/api/etat` | État complet. |
| `WS` | `/api/ws` | État poussé à chaque changement ; envoyer `ping` pour recevoir l'heure du serveur. |
| `POST` | `/api/lacher` | `{heure?, source?}` : nouvelle flèche. |
| `POST` | `/api/impact` | `{fleche_id?, x_mm, y_mm, diametre_mm, score?, image_jpeg_b64?}` : impact (repère : centre du blason, y vers le haut). |
| `POST` | `/api/commande` | `{action, …}` : voir ci-dessous. |
| `POST` | `/api/recharger` | Relit `arc-replay.yml` et reconfigure MediaMTX. |
| `GET` | `/api/sante` | Contrôle de vie. |

Actions de `/api/commande` :

| `action` | Paramètres |
|---|---|
| `delai` | `valeur` (secondes) |
| `lateralite` | `valeur` : `droitier` ou `gaucher` |
| `disposition` | `ordre` (tous les id), `masquees` |
| `focus` | `camera` (ou absent pour revenir à la mosaïque) |
| `qr` | `valeur` : booléen |
| `rejeu` | `fleche_id` (`derniere` par défaut), `vitesse` |
| `rejeu_controle` | `lecture`, `vitesse`, `redemarrer` |
| `rejeu_fermer` | — |
| `nouvelle_volee`, `nouvelle_seance`, `marquer` | — |
| `export_usb` | `portee` : `seance` ou `tout` |

Tout autre déclencheur de lâcher (capteur sur l'arc, bouton physique sur un GPIO…) n'a qu'à appeler `POST /api/lacher`.
