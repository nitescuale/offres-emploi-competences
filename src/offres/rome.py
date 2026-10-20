"""Référentiel ROME 4.0 (France Travail, open data sur data.gouv.fr) : métiers, appellations, compétences, savoirs.

Les noms de fichiers changent à chaque version du ROME : on prend toutes les ressources du jeu de données et on
garde les fichiers CSV qu'elles contiennent.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import requests

JEU_ROME = "58da857388ee384902e505f5"
URL_JEU = f"https://www.data.gouv.fr/api/1/datasets/{JEU_ROME}/"


def telecharger(cible: Path) -> list[Path]:
    cible.mkdir(parents=True, exist_ok=True)
    jeu = requests.get(URL_JEU, timeout=60)
    jeu.raise_for_status()
    ecrits: list[Path] = []
    for ressource in jeu.json()["resources"]:
        url, titre = ressource["url"], ressource.get("title", "")
        print(f"- {titre} ({ressource.get('format')}, {ressource.get('filesize')} o, {ressource.get('last_modified')}) {url}")
        r = requests.get(url, timeout=300)
        if r.status_code != 200:
            print(f"  ignoré : {r.status_code}")
            continue
        contenu = r.content
        if zipfile.is_zipfile(io.BytesIO(contenu)):
            with zipfile.ZipFile(io.BytesIO(contenu)) as z:
                for nom in z.namelist():
                    if nom.lower().endswith((".csv", ".json", ".xlsx")):
                        chemin = cible / Path(nom).name
                        chemin.write_bytes(z.read(nom))
                        ecrits.append(chemin)
        elif url.lower().endswith((".csv", ".json", ".xlsx")):
            chemin = cible / Path(url.split("?")[0]).name
            chemin.write_bytes(contenu)
            ecrits.append(chemin)
    for chemin in ecrits:
        print(f"  {chemin.name} : {chemin.stat().st_size / 1e3:.0f} ko")
    return ecrits
