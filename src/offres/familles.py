"""Regroupements de métiers utilisés dans les analyses."""

from __future__ import annotations

import polars as pl

# Métiers de la data dans le répertoire des métiers de la fonction publique (après harmonisation des libellés)
MOTIF_DATA = (
    r"(?i)^(data |analyste (de|des) données|chargée / chargé de collecte et d'exploitation de données|"
    r"experte / expert en (production, traitement et analyse de données|information statistique)|"
    r"technicienne / technicien en production, traitement et analyse de données|statisticienne|"
    r"responsable d'un programme d'études et statistiques|directrice / directeur des données|"
    r"administratrice / administrat\w+ de bases de données)"
)


def est_data(colonne: str = "metier") -> pl.Expr:
    return pl.col(colonne).str.contains(MOTIF_DATA).fill_null(False)
