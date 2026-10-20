"""Postes qui peinent à recruter : une annonce est dite « republiée » quand le même poste (même organisme, métier,
intitulé et département) est remis en ligne entre 7 et 180 jours après. Le service public ne publie pas de salaire ;
cette cible de repli mesure la difficulté de recrutement telle que l'employeur la révèle en republiant.

Les variables ne prennent que ce qui est connu le jour de la publication (y compris l'historique de republication du
même poste), pour qu'un modèle entraîné sur le passé puisse servir sur les annonces à venir.
"""

from __future__ import annotations

import datetime as dt

import polars as pl

POSTE = ["organisme", "metier", "intitule_norme", "departement"]
MIN_JOURS, MAX_JOURS = 7, 180

CATEGORIELLES = ["metier", "departement", "organisme", "versant", "categorie", "nature_emploi", "statut_poste",
                 "experience"]
NUMERIQUES = ["teletravail", "management", "temps_plein", "niveau_etudes", "mois", "postes_annonce", "texte_competences",
              "deja_republiee", "publications_avant"]


def republications(offres: pl.DataFrame, min_jours: int = MIN_JOURS, max_jours: int = MAX_JOURS) -> pl.DataFrame:
    """Une ligne par annonce, avec `republiee` (le même poste revient entre `min_jours` et `max_jours` après) et
    l'historique du poste à la date de publication. Les annonces trop récentes pour qu'on sache si elles reviendront
    (moins de `max_jours` avant la dernière publication du fichier) sont écartées."""
    fin = offres["date_publication"].max()
    a = (offres.unique("annonce_id").filter(pl.col("date_publication") >= dt.date(2022, 1, 1))
         .with_columns(intitule_norme=pl.col("intitule").str.to_lowercase().str.replace_all(r"\W+", " ").str.strip_chars())
         .sort("date_publication", "annonce_id"))
    suivante = (pl.col("date_publication").shift(-1).over(POSTE) - pl.col("date_publication")).dt.total_days()
    precedente = (pl.col("date_publication") - pl.col("date_publication").shift(1).over(POSTE)).dt.total_days()
    a = a.with_columns(jours_suivante=suivante, jours_precedente=precedente,
                       publications_avant=pl.int_range(pl.len()).over(POSTE))
    return (a.with_columns(republiee=pl.col("jours_suivante").is_between(min_jours, max_jours).fill_null(False),
                           deja_republiee=pl.col("jours_precedente").is_between(min_jours, max_jours).fill_null(False))
            .filter(pl.col("date_publication") <= fin - dt.timedelta(days=max_jours)))


def variables(a: pl.DataFrame):
    """Tableau pandas des variables du modèle (catégories en type `category`, booléens en flottants, vides gardés)."""
    x = a.with_columns(mois=pl.col("date_publication").dt.month(),
                       texte_competences=pl.col("competences_texte").is_not_null(),
                       deja_republiee=pl.col("deja_republiee"))
    x = x.select(CATEGORIELLES + NUMERIQUES).with_columns(
        pl.col(["teletravail", "management", "temps_plein", "texte_competences", "deja_republiee"]).cast(pl.Float64))
    return x.to_pandas().astype({c: "category" for c in CATEGORIELLES})


def aligner(test, apprentissage):
    """Mêmes catégories que l'apprentissage (une modalité nouvelle devient manquante), comme en production."""
    test = test.copy()
    for c in CATEGORIELLES:
        test[c] = test[c].cat.set_categories(apprentissage[c].cat.categories)
    return test
