"""Référentiel ROME 4.0 (France Travail, open data sur data.gouv.fr) : métiers, appellations, compétences, savoirs.

Les noms de fichiers changent à chaque version du ROME : on prend toutes les ressources du jeu de données et on
garde les fichiers CSV qu'elles contiennent.
"""

from __future__ import annotations

import io
import time
import zipfile
from pathlib import Path

import requests

JEU_ROME = "58da857388ee384902e505f5"
URL_JEU = f"https://www.data.gouv.fr/api/1/datasets/{JEU_ROME}/"


# Certains serveurs de France Travail coupent la connexion aux clients sans navigateur déclaré
ENTETES = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) offres-emploi-competences (github.com/nitescuale)"}
FORMATS = {"csv", "json", "xlsx", "zip"}


def _get(url: str) -> requests.Response | None:
    for essai in range(3):
        try:
            r = requests.get(url, timeout=300, headers=ENTETES)
            if r.status_code == 200:
                return r
            print(f"  code {r.status_code}")
        except requests.RequestException as e:
            print(f"  essai {essai + 1} : {e}")
        time.sleep(5 * (essai + 1))
    return None


def telecharger(cible: Path) -> list[Path]:
    cible.mkdir(parents=True, exist_ok=True)
    jeu = requests.get(URL_JEU, timeout=60, headers=ENTETES)
    jeu.raise_for_status()
    ecrits: list[Path] = []
    for ressource in jeu.json()["resources"]:
        url, titre = ressource["url"], ressource.get("title", "")
        fmt = (ressource.get("format") or "").lower()
        print(f"- {titre} ({fmt}, {ressource.get('last_modified')}) {url}")
        if fmt not in FORMATS:
            continue
        r = _get(url)
        if r is None:
            print("  ignoré")
            continue
        contenu = r.content
        if zipfile.is_zipfile(io.BytesIO(contenu)):
            with zipfile.ZipFile(io.BytesIO(contenu)) as z:
                for nom in z.namelist():
                    if nom.lower().endswith((".csv", ".json", ".xlsx")):
                        chemin = cible / Path(nom).name
                        chemin.write_bytes(z.read(nom))
                        ecrits.append(chemin)
        else:
            nom = Path(url.split("?")[0]).name
            chemin = cible / (nom if "." in nom else f"rome_complet.{fmt}")
            chemin.write_bytes(contenu)
            ecrits.append(chemin)
    if not ecrits:
        raise SystemExit("Aucun fichier du ROME téléchargé")
    for chemin in ecrits:
        print(f"  {chemin.name} : {chemin.stat().st_size / 1e3:.0f} ko")
    return ecrits
