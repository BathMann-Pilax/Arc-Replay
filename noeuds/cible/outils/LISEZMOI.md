# Outils de détection (reportés)

Ces scripts ne sont utilisés par aucun service. Ils servent à reprendre plus tard
la détection d'impact avec une caméra **face au blason** (caméra HQ au pas de tir).

| Fichier | Rôle |
|---|---|
| `detection.py` | Détection « vue de face » : recalage ECC du blason (`aligner`), carte de changements en contraste relatif (`carte_changements`), regroupement des morceaux de tube, exclusion des flèches déjà plantées (comparaison avant/après d'un même tir), point d'entrée = bout fin du tube (`point_entree`). |
| `test_impact.py` | Essai sur le Pi, sans serveur Arc Replay : aperçu avec grille, recadrage, calibration sur 4 points du bord du blason, puis une ligne par flèche (position en mm, score) et une image annotée. |

Utilisation (sur le Pi, avec OpenCV : `sudo apt install python3-opencv python3-numpy`) :

```bash
cd noeuds/cible/outils
python3 test_impact.py apercu
python3 test_impact.py cadrer --crop 0.40,0.35,0.20,0.20
python3 test_impact.py points HX,HY DX,DY BX,BY GX,GY --diametre 400
python3 test_impact.py test
```

Arrêtez d'abord le service de la vue cible (`sudo systemctl stop arc-replay-cible`) : un seul
programme peut utiliser la caméra à la fois.

Le `detection.py` de ce dossier est distinct de `noeuds/cible/detection.py`, utilisé par le
service en mode `detection: true` (caméra dans le coffre de la cible).
