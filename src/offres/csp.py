"""Offres de « Choisir le service public » (open data DGAFP sur data.gouv.fr) : un fichier CSV par année depuis 2022.

Source de repli sans identifiants : toutes les offres d'emploi des trois fonctions publiques, avec leur texte.
"""

from __future__ import annotations

import io
from pathlib import Path

import polars as pl
import requests

JEU_CSP = "6322e99e12175f7eb26ff465"
URL_JEU = f"https://www.data.gouv.fr/api/1/datasets/{JEU_CSP}/"
ENTETES = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) offres-emploi-competences (github.com/nitescuale)"}


def lire_csv(contenu: bytes) -> pl.DataFrame:
    """Le séparateur et l'encodage ne sont pas documentés : on essaie les combinaisons courantes."""
    erreurs = []
    for encodage in ("utf8", "latin1"):
        texte = contenu.decode("utf-8" if encodage == "utf8" else "latin-1", errors="strict" if encodage == "utf8" else "replace")
        premiere = texte.split("\n", 1)[0]
        separateur = max([";", ",", "\t", "|"], key=premiere.count)
        try:
            return pl.read_csv(io.StringIO(texte), separator=separateur, infer_schema=False, truncate_ragged_lines=True)
        except Exception as e:  # noqa: BLE001
            erreurs.append(f"{encodage}/{separateur!r}: {e}")
    raise ValueError(" ; ".join(erreurs))


def telecharger(cible: Path) -> list[Path]:
    cible.mkdir(parents=True, exist_ok=True)
    jeu = requests.get(URL_JEU, timeout=60, headers=ENTETES)
    jeu.raise_for_status()
    ecrits = []
    for ressource in jeu.json()["resources"]:
        titre, fmt, url = ressource.get("title", ""), (ressource.get("format") or "").lower(), ressource["url"]
        print(f"- {titre} ({fmt}, {ressource.get('filesize')} o, {ressource.get('last_modified')}) {url}")
        if fmt == "pdf" or fmt == "xlsx":
            r = requests.get(url, timeout=300, headers=ENTETES)
            if r.status_code == 200:
                chemin = cible / f"doc_{Path(url.split('?')[0]).name}"
                chemin.write_bytes(r.content)
                ecrits.append(chemin)
            continue
        if fmt != "csv":
            continue
        r = requests.get(url, timeout=600, headers=ENTETES)
        if r.status_code != 200:
            print(f"  code {r.status_code}")
            continue
        table = lire_csv(r.content)
        nom = "".join(c if c.isalnum() else "_" for c in titre.lower()).strip("_")[:60] or ressource["id"]
        chemin = cible / f"{nom}.parquet"
        table.write_parquet(chemin, compression="zstd")
        ecrits.append(chemin)
        print(f"  {table.height} lignes, {table.width} colonnes -> {chemin.name}")
        for col in table.columns:
            serie = table[col]
            longueur = serie.str.len_chars().mean() if serie.dtype == pl.Utf8 else None
            exemple = next((v for v in serie.head(50).to_list() if v), None)
            print(f"    {col} : {serie.null_count()} vides, longueur moy. {longueur}, ex. {str(exemple)[:160]!r}")
    return ecrits
