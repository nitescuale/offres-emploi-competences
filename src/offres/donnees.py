"""Accès aux fichiers publiés dans la release `donnees` du dépôt, avec un cache local dans `data/`."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import requests

URL_RELEASE = "https://github.com/nitescuale/offres-emploi-competences/releases/download/donnees"
CACHE = Path(__file__).resolve().parents[2] / "data"


def chemin(nom: str, rafraichir: bool = False) -> Path:
    """Chemin local du fichier `nom` de la release, téléchargé au besoin."""
    CACHE.mkdir(exist_ok=True)
    local = CACHE / nom
    if rafraichir or not local.exists():
        r = requests.get(f"{URL_RELEASE}/{nom}", timeout=600)
        r.raise_for_status()
        local.write_bytes(r.content)
    return local


def offres_service_public(rafraichir: bool = False) -> pl.DataFrame:
    return pl.read_parquet(chemin("csp_offres.parquet", rafraichir))


def rome(table: str) -> pl.DataFrame:
    """Une table du ROME 4.0, par ex. `referentiel_competence`, `referentiel_savoir`, `coherence_item`."""
    return pl.read_csv(chemin(f"rome_unix_{table}_v462_utf8.csv"), infer_schema=False)
