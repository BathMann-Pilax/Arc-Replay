"""Détection de la clé USB et export des séances."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable, Optional


def statut(chemin: str, verifier_montage: bool = True) -> dict:
    p = Path(chemin)
    presente = os.path.ismount(p) if verifier_montage else p.is_dir()
    libre_go = None
    if presente:
        try:
            libre_go = round(shutil.disk_usage(p).free / 1e9, 1)
        except OSError:
            presente = False
    return {"presente": presente, "libre_go": libre_go}


def fichiers_a_copier(source: Path) -> list[Path]:
    return sorted(
        p for p in source.rglob("*") if p.is_file() and not p.name.endswith(".part")
    )


def exporter(
    sources: list[Path],
    destination: Path,
    progression: Optional[Callable[[int, int], None]] = None,
) -> tuple[int, int]:
    """Copie chaque dossier de séance dans `destination`.

    Un fichier déjà présent avec la même taille est ignoré : on peut relancer
    l'export après chaque volée sans tout recopier.
    Renvoie (fichiers copiés, fichiers ignorés).
    """
    a_copier = [(src, f) for src in sources for f in fichiers_a_copier(src)]
    total, copies, ignores = len(a_copier), 0, 0
    for i, (racine, fichier) in enumerate(a_copier, start=1):
        cible = destination / racine.name / fichier.relative_to(racine)
        if cible.exists() and cible.stat().st_size == fichier.stat().st_size:
            ignores += 1
        else:
            cible.parent.mkdir(parents=True, exist_ok=True)
            # copyfile : pas de copie des droits, que FAT/exFAT ne gèrent pas
            shutil.copyfile(fichier, cible)
            copies += 1
        if progression:
            progression(i, total)
    os.sync()  # tout est écrit sur la clé avant d'annoncer qu'on peut la retirer
    return copies, ignores
