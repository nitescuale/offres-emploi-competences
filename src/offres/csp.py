"""Offres de « Choisir le service public » (open data DGAFP sur data.gouv.fr) : un fichier CSV par année depuis 2022.

Source principale du projet, sans identifiants : toutes les offres d'emploi des trois fonctions publiques.
Dictionnaire des colonnes : docs/dictionnaire-donnees.md.
"""

from __future__ import annotations

import io
import json
import time
from datetime import date
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


def _get(url: str, essais: int = 4) -> requests.Response:
    for essai in range(essais):
        try:
            r = requests.get(url, timeout=600, headers=ENTETES)
            if r.status_code == 200:
                return r
            print(f"  code {r.status_code}")
        except requests.RequestException as e:
            print(f"  essai {essai + 1} : {e}")
        time.sleep(10 * (essai + 1))
    raise SystemExit(f"Échec du téléchargement de {url} après {essais} essais")


def telecharger(cible: Path, rapport_precedent: Path | None = None) -> Path:
    """Télécharge chaque fichier annuel, normalise, consolide en un seul Parquet et écrit un rapport.

    Échoue (sans rien publier) si un fichier ne se télécharge pas, ou si le résultat a nettement moins d'offres ou de
    fichiers que la fois précédente : mieux vaut garder l'ancien Parquet qu'en publier un amputé d'une année.
    """
    cible.mkdir(parents=True, exist_ok=True)
    jeu = requests.get(URL_JEU, timeout=60, headers=ENTETES)
    jeu.raise_for_status()
    annees = []
    for ressource in jeu.json()["resources"]:
        titre, fmt, url = ressource.get("title", ""), (ressource.get("format") or "").lower(), ressource["url"]
        print(f"- {titre} ({fmt}, {ressource.get('filesize')} o, {ressource.get('last_modified')}) {url}")
        if fmt not in ("pdf", "xlsx", "csv"):
            continue
        r = _get(url)
        if fmt != "csv":
            (cible / f"doc_{Path(url.split('?')[0]).name}").write_bytes(r.content)
            continue
        brut = lire_csv(r.content)
        # La date de mise à jour de la ressource sert à départager une offre présente dans deux fichiers
        annees.append(normaliser(brut, f"{ressource.get('last_modified', '')} {titre}"))
        print(f"  {brut.height} lignes, {brut.width} colonnes ; ignorées : {sorted(set(brut.columns) - set(COLONNES))}")
    if not annees:
        raise SystemExit("Aucun fichier d'offres lu")
    offres = consolider(annees)
    rapport = {
        "offres": offres.height,
        "annonces_distinctes": offres["annonce_id"].n_unique(),
        "lignes_brutes": sum(a.height for a in annees),
        "fichiers": len(annees),
        "premiere_publication": str(offres["date_publication"].min()),
        "derniere_publication": str(offres["date_publication"].max()),
        "avec_texte_competences": int(offres["competences_texte"].is_not_null().sum()),
        "sans_departement": int(offres["departement"].is_null().sum()),
        "dates_ecartees": DATES_ECARTEES.get("n", 0),
        "par_annee": {str(k): v for k, v in offres.group_by(pl.col("date_publication").dt.year()).len().sort("date_publication").iter_rows()},
    }
    if rapport_precedent and rapport_precedent.exists():
        avant = json.loads(rapport_precedent.read_text())
        if rapport["fichiers"] < avant.get("fichiers", 0) or rapport["offres"] < 0.95 * avant.get("offres", 0):
            raise SystemExit(f"Régression : {rapport['fichiers']} fichiers / {rapport['offres']} offres contre "
                             f"{avant.get('fichiers')} / {avant.get('offres')} la fois précédente ; rien n'est publié")
    chemin = cible / "offres.parquet"
    offres.write_parquet(chemin, compression="zstd")
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
# Colonnes qui éclatent une offre en plusieurs lignes dans la source (une ligne par spécialisation ou par langue)
MULTIVALUEES = ["specialisation", "langues", "langues_niveaux"]
# Années hors de cette plage = fautes de frappe (1922, 2926, 9999-12-31...)
DATE_MIN, DATE_MAX = date(2015, 1, 1), date(2030, 12, 31)
DATES_ECARTEES: dict[str, int] = {}


def departement_depuis_code_postal(code: pl.Expr) -> pl.Expr:
    """Code postal -> département ; Corse : 200xx-201xx en Corse-du-Sud, 202xx-206xx en Haute-Corse."""
    return (
        pl.when(code.str.starts_with("97") | code.str.starts_with("98")).then(code.str.slice(0, 3))
        .when(code.str.starts_with("20")).then(pl.when(code.str.slice(0, 3) <= "201").then(pl.lit("2A")).otherwise(pl.lit("2B")))
        .otherwise(code.str.slice(0, 2))
    )


def normaliser(brut: pl.DataFrame, fichier: str) -> pl.DataFrame:
    """Une année brute -> colonnes nommées et typées."""
    renomme = brut.rename({k: v for k, v in COLONNES.items() if k in brut.columns})
    table = renomme.select(
        [pl.col(v).cast(pl.Utf8) if v in renomme.columns else pl.lit(None, dtype=pl.Utf8).alias(v) for v in COLONNES.values()]
    )
    texte = [c for c in table.columns if table[c].dtype == pl.Utf8]
    table = (
        table.with_columns(
            # Valeurs vides déguisées : « None », espaces, « Non renseigné »
            [pl.when(pl.col(c).str.strip_chars().is_in(["", "None", "Non renseigné"])).then(None)
             .otherwise(pl.col(c).str.strip_chars()).alias(c) for c in texte]
        )
        .with_columns(
            [pl.col(c).str.to_date("%d/%m/%Y", strict=False) for c in DATES]
            + [pl.col(c).replace_strict({"Oui": True, "Non": False}, default=None, return_dtype=pl.Boolean) for c in OUI_NON]
            + [
                pl.col("localisation").str.extract(r"\((\w+)\s*\)\s*$").str.to_uppercase().str.zfill(2).alias("departement"),
                pl.col("localisation").str.replace(r"\s*\(\w+\s*\)\s*$", "").alias("departement_nom"),
                pl.col("categorie_libelle").str.extract(r"Catégorie (A\+|A|B|C)").alias("categorie"),
                pl.col("niveau_etudes_libelle").str.extract(r"Niveau (\d)").cast(pl.Int8).alias("niveau_etudes"),
                # « Cadre », « Employé »... égarés dans le statut du poste (colonnes décalées dans la source)
                pl.when(pl.col("statut_poste").is_in(["Vacant", "Susceptible d'être vacant"])).then(pl.col("statut_poste"))
                .alias("statut_poste"),
                pl.lit(fichier).alias("fichier_source"),
            ]
        )
    )
    ecartees = sum(int(((table[c] < DATE_MIN) | (table[c] > DATE_MAX)).sum()) for c in DATES)
    DATES_ECARTEES["n"] = DATES_ECARTEES.get("n", 0) + ecartees
    return table.with_columns(
        [pl.when(pl.col(c).is_between(DATE_MIN, DATE_MAX)).then(pl.col(c)).alias(c) for c in DATES]
        + [
            # Département manquant : on le retrouve par le code postal du lieu d'affectation quand il y en a un
            pl.coalesce(
                "departement",
                departement_depuis_code_postal(pl.col("lieu_affectation").str.extract(r"\b(\d{5})\b")),
            ).alias("departement"),
            # Même métier écrit de plusieurs façons d'une année à l'autre : astérisques, apostrophes typographiques
            pl.col("metier").str.replace_all(r"^\*|\*$", "").str.replace_all("’", "'").str.replace_all(r"\s+", " ")
            .str.strip_chars(),
        ]
    )


def consolider(annees: list[pl.DataFrame]) -> pl.DataFrame:
    """Une ligne par référence.

    - Une référence présente dans plusieurs fichiers garde la version du fichier le plus récent.
    - Les lignes éclatées par spécialisation ou par langue sont regroupées (valeurs jointes par « | »).
    - Le versant manquant est déduit de l'organisme de rattachement quand celui-ci n'a qu'un versant.
    - `annonce_id` repère les annonces multi-postes : mêmes champs, références différentes.
    """
    toutes = pl.concat(annees, how="diagonal_relaxed").with_row_index("_ordre")
    dernier = toutes.group_by("reference").agg(pl.col("fichier_source").max().alias("_dernier"))
    toutes = toutes.join(dernier, on="reference").filter(pl.col("fichier_source") == pl.col("_dernier")).drop("_dernier")
    autres = [c for c in toutes.columns if c not in MULTIVALUEES and c not in ("reference", "_ordre")]
    offres = (
        toutes.sort("_ordre")
        .group_by("reference", maintain_order=True)
        .agg(
            [pl.col(c).first() for c in autres]
            + [pl.col(c).drop_nulls().unique(maintain_order=True).str.join(" | ").alias(c) for c in MULTIVALUEES]
        )
        .with_columns([pl.when(pl.col(c) == "").then(None).otherwise(pl.col(c)).alias(c) for c in MULTIVALUEES])
    )
    versant_unique = (
        offres.filter(pl.col("versant").is_not_null()).group_by("organisme")
        .agg(pl.col("versant").unique().alias("_v")).filter(pl.col("_v").list.len() == 1)
        .select("organisme", pl.col("_v").list.first().alias("_versant"))
    )
    cles = [c for c in COLONNES.values() if c != "reference"]
    return (
        offres.join(versant_unique, on="organisme", how="left")
        .with_columns(pl.coalesce("versant", "_versant").alias("versant"))
        .drop("_versant")
        .with_columns(pl.concat_str([pl.col(c).cast(pl.Utf8).fill_null("∅") for c in cles], separator="\x1f")
                      .hash().alias("annonce_id"))
        .with_columns(pl.len().over("annonce_id").alias("postes_annonce"))
        .select(["reference"] + [c for c in COLONNES.values() if c != "reference"]
                + ["departement", "departement_nom", "categorie", "niveau_etudes", "annonce_id", "postes_annonce", "fichier_source"])
        .sort("date_publication", "reference", nulls_last=True)
    )
