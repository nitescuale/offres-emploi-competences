"""Offres de « Choisir le service public » (open data DGAFP sur data.gouv.fr) : un fichier CSV par année depuis 2022.

Source de repli sans identifiants : toutes les offres d'emploi des trois fonctions publiques, avec leur texte.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import polars as pl
import requests

JEU_CSP = "6322e99e12175f7eb26ff465"
URL_JEU = f"https://www.data.gouv.fr/api/1/datasets/{JEU_CSP}/"
ENTETES = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) offres-emploi-competences (github.com/nitescuale)"}


def lire_csv(contenu: bytes) -> pl.DataFrame:
    """Le séparateur et l'encodage ne sont pas documentés : UTF-8 si possible, sinon Latin-1 ; séparateur deviné."""
    try:
        texte = contenu.decode("utf-8")
    except UnicodeDecodeError:
        texte = contenu.decode("latin-1")
    premiere = texte.split("\n", 1)[0]
    separateur = max([";", ",", "\t", "|"], key=premiere.count)
    return pl.read_csv(io.StringIO(texte), separator=separateur, infer_schema=False, truncate_ragged_lines=True)


def telecharger(cible: Path) -> Path:
    """Télécharge chaque fichier annuel, normalise, consolide en un seul Parquet et écrit un rapport."""
    cible.mkdir(parents=True, exist_ok=True)
    jeu = requests.get(URL_JEU, timeout=60, headers=ENTETES)
    jeu.raise_for_status()
    annees = []
    for ressource in jeu.json()["resources"]:
        titre, fmt, url = ressource.get("title", ""), (ressource.get("format") or "").lower(), ressource["url"]
        print(f"- {titre} ({fmt}, {ressource.get('filesize')} o, {ressource.get('last_modified')}) {url}")
        r = requests.get(url, timeout=600, headers=ENTETES)
        if r.status_code != 200:
            print(f"  code {r.status_code}")
            continue
        if fmt in ("pdf", "xlsx"):
            (cible / f"doc_{Path(url.split('?')[0]).name}").write_bytes(r.content)
            continue
        if fmt != "csv":
            continue
        brut = lire_csv(r.content)
        annees.append(normaliser(brut, titre))
        print(f"  {brut.height} lignes, {brut.width} colonnes ; inconnues : {sorted(set(brut.columns) - set(COLONNES))}")
    if not annees:
        raise SystemExit("Aucun fichier d'offres lu")
    offres = consolider(annees)
    chemin = cible / "offres.parquet"
    offres.write_parquet(chemin, compression="zstd")
    rapport = {
        "offres": offres.height,
        "lignes_brutes": sum(a.height for a in annees),
        "fichiers": len(annees),
        "premiere_publication": str(offres["date_publication"].min()),
        "derniere_publication": str(offres["date_publication"].max()),
        "avec_texte_competences": int(offres["competences_texte"].is_not_null().sum()),
        "sans_departement": int(offres["departement"].is_null().sum()),
        "par_annee": {str(k): v for k, v in offres.group_by(pl.col("date_publication").dt.year()).len().sort("date_publication").iter_rows()},
    }
    (cible / "rapport.json").write_text(json.dumps(rapport, ensure_ascii=False, indent=1))
    print(json.dumps(rapport, ensure_ascii=False, indent=1))
    return chemin


# Colonnes du CSV -> noms courts. Les colonnes absentes d'une année sont laissées vides.
COLONNES = {
    "Référence": "reference",
    "Organisme de rattachement": "organisme",
    "Versant": "versant",
    "Employeur": "employeur",
    "Métier": "metier",
    "Intitulé du poste": "intitule",
    "Catégorie": "categorie_libelle",
    "Statut du poste": "statut_poste",
    "Nature de l'emploi": "nature_emploi",
    "Nature de contrat": "nature_contrat",
    "Durée du contrat": "duree_contrat",
    "Localisation du poste": "localisation",
    "Lieu d'affectation": "lieu_affectation",
    "Lieu d'affectation (sans géolocalisation)": "commune",
    "Niveau d'études": "niveau_etudes_libelle",
    "Niveau d'expérience min. requis": "experience",
    "Spécialisation": "specialisation",
    "Télétravail": "teletravail",
    "Management": "management",
    "Temps Plein": "temps_plein",
    "Langues": "langues",
    "Niveaux": "langues_niveaux",
    "Date de première publication": "date_publication",
    "Date de début de publication par défaut": "date_debut_publication",
    "Date de fin de publication par défaut": "date_fin_publication",
    "Date de vacance de l'emploi": "date_vacance",
    "Compétences attendues": "competences_texte",
    "Documents à transmettre": "documents",
    "Avis de vacances au JO": "avis_jo",
}
DATES = ["date_publication", "date_debut_publication", "date_fin_publication", "date_vacance"]
OUI_NON = ["teletravail", "management", "temps_plein"]


def normaliser(brut: pl.DataFrame, fichier: str) -> pl.DataFrame:
    """Une année brute -> colonnes nommées et typées, une ligne par offre."""
    renomme = brut.rename({k: v for k, v in COLONNES.items() if k in brut.columns})
    table = renomme.select(
        [pl.col(v).cast(pl.Utf8) if v in renomme.columns else pl.lit(None, dtype=pl.Utf8).alias(v) for v in COLONNES.values()]
    )
    texte = [c for c in table.columns if table[c].dtype == pl.Utf8]
    return (
        table.with_columns(
            # Valeurs vides déguisées : « None », espaces, « Non renseigné »
            [pl.when(pl.col(c).str.strip_chars().is_in(["", "None", "Non renseigné"])).then(None)
             .otherwise(pl.col(c).str.strip_chars()).alias(c) for c in texte]
        )
        .with_columns(
            [pl.col(c).str.to_date("%d/%m/%Y", strict=False) for c in DATES]
            + [pl.col(c).replace_strict({"Oui": True, "Non": False}, default=None, return_dtype=pl.Boolean) for c in OUI_NON]
            + [
                pl.col("localisation").str.extract(r"\((\w+)\s*\)\s*$").str.to_uppercase().alias("departement"),
                pl.col("localisation").str.replace(r"\s*\(\w+\s*\)\s*$", "").alias("departement_nom"),
                pl.col("categorie_libelle").str.extract(r"Catégorie (A\+|A|B|C)").alias("categorie"),
                pl.col("niveau_etudes_libelle").str.extract(r"Niveau (\d)").cast(pl.Int8).alias("niveau_etudes"),
                pl.lit(fichier).alias("fichier_source"),
            ]
        )
        .with_columns(pl.col("departement").str.zfill(2))
    )


def consolider(annees: list[pl.DataFrame]) -> pl.DataFrame:
    """Empile les années ; une offre présente dans plusieurs fichiers garde la version du fichier le plus récent."""
    return (
        pl.concat(annees, how="diagonal_relaxed")
        .sort("fichier_source")
        .unique("reference", keep="last", maintain_order=True)
        .sort("date_publication", "reference", nulls_last=True)
    )
