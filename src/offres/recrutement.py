"""Postes qui peinent à recruter : une annonce est dite « republiée » quand le même poste (même organisme, métier,
intitulé et département) est remis en ligne entre 7 et 180 jours après. Le service public ne publie pas de salaire ;
cette cible de repli mesure la difficulté de recrutement telle que l'employeur la révèle en republiant.

Les variables ne prennent que ce qui est connu le jour de la publication : l'historique du poste ne compte que les
publications des jours strictement antérieurs, sur une fenêtre glissante d'un an, pour garder le même sens d'une année
à l'autre (le fichier commence en 2022 : un historique cumulé grossirait mécaniquement avec le temps).
"""

from __future__ import annotations

import datetime as dt

import polars as pl

POSTE = ["organisme", "metier", "intitule_norme", "departement"]
MIN_JOURS, MAX_JOURS = 7, 180
HISTORIQUE_JOURS = 365

CATEGORIELLES = ["metier", "departement", "organisme", "versant", "categorie", "nature_emploi", "statut_poste",
                 "experience"]
NUMERIQUES = ["teletravail", "management", "temps_plein", "niveau_etudes", "mois", "postes_annonce",
              "publications_an", "deja_republiee"]


def _par_poste(a: pl.DataFrame, decalage: int, sens: str) -> pl.Series:
    """Date de la publication du même poste la plus proche de `date + decalage` jours, vers l'avant ou l'arrière."""
    dates = a.select(*POSTE, date_autre=pl.col("date_publication")).unique().sort("date_autre")
    cible = a.select(*POSTE, cible=pl.col("date_publication") + dt.timedelta(days=decalage)).with_row_index("i")
    j = cible.sort("cible").join_asof(dates, left_on="cible", right_on="date_autre", by=POSTE, strategy=sens,
                                       check_sortedness=False)  # triés par date, `by` empêche la vérification
    return j.sort("i")["date_autre"]


def _publications_avant(a: pl.DataFrame, jours: int) -> pl.Series:
    """Nombre de publications du même poste dans les `jours` jours précédents, jour même exclu."""
    cumul = (a.group_by(*POSTE, "date_publication").len().sort("date_publication")
             .with_columns(cumul=pl.col("len").cum_sum().over(POSTE)).drop("len"))
    def jusqua(decalage):
        c = a.select(*POSTE, cible=pl.col("date_publication") - dt.timedelta(days=decalage)).with_row_index("i")
        j = c.sort("cible").join_asof(cumul, left_on="cible", right_on="date_publication", by=POSTE, strategy="backward",
                                      check_sortedness=False)
        return j.sort("i")["cumul"].fill_null(0)
    return jusqua(1) - jusqua(jours + 1)


def republications(offres: pl.DataFrame, min_jours: int = MIN_JOURS, max_jours: int = MAX_JOURS) -> pl.DataFrame:
    """Une ligne par annonce, avec `republiee` (le même poste revient au moins une fois entre `min_jours` et `max_jours`
    après, même si un doublon le précède de quelques jours) et l'historique du poste à la date de publication.

    Sont écartées : les annonces sans métier ou sans département (le poste n'est pas identifiable) et les annonces trop
    récentes pour qu'on sache si elles reviendront (moins de `max_jours` avant la dernière publication du fichier)."""
    fin = offres["date_publication"].max()
    a = (offres.sort("annonce_id", "reference").unique("annonce_id", keep="first", maintain_order=True)
         .filter(pl.col("date_publication") >= dt.date(2022, 1, 1)).drop_nulls(["metier", "departement", "organisme"])
         .with_columns(intitule_norme=pl.col("intitule").str.to_lowercase().str.replace_all(r"\W+", " ").str.strip_chars())
         .sort("date_publication", "annonce_id"))
    suivante = _par_poste(a, min_jours, "forward")
    precedente = _par_poste(a, -min_jours, "backward")
    a = a.with_columns(
        republiee=((suivante - pl.col("date_publication")).dt.total_days() <= max_jours).fill_null(False),
        deja_republiee=((pl.col("date_publication") - precedente).dt.total_days() <= max_jours).fill_null(False),
        publications_an=_publications_avant(a, HISTORIQUE_JOURS),
    )
    return a.filter(pl.col("date_publication") <= fin - dt.timedelta(days=max_jours))


def variables(a: pl.DataFrame):
    """Tableau pandas des variables du modèle (catégories en type `category`, booléens en flottants, vides gardés)."""
    x = a.with_columns(mois=pl.col("date_publication").dt.month()).select(CATEGORIELLES + NUMERIQUES)
    x = x.with_columns(pl.col(["teletravail", "management", "temps_plein", "deja_republiee"]).cast(pl.Float64))
    return x.to_pandas().astype({c: "category" for c in CATEGORIELLES})


def aligner(test, apprentissage):
    """Mêmes catégories que l'apprentissage (une modalité nouvelle devient manquante), comme en production."""
    test = test.copy()
    for c in CATEGORIELLES:
        test[c] = test[c].cat.set_categories(apprentissage[c].cat.categories)
    return test
