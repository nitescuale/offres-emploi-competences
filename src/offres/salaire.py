"""Lecture du salaire affiché par France Travail, par ex. « Annuel de 35000.0 Euros à 45000.0 Euros sur 12 mois ».

Tout est ramené en brut annuel. Un salaire horaire est converti sur la base de 151,67 h par mois (35 h) ; les offres
à temps partiel donnent donc un brut annuel « équivalent temps plein » seulement si l'on passe par l'horaire.
"""

from __future__ import annotations

import re

import polars as pl

HEURES_MOIS = 151.67
_NOMBRE = r"(\d+(?:[.,]\d+)?)"
_MOTIF = re.compile(
    rf"^(?P<periode>Annuel|Mensuel|Horaire|Hebdomadaire|Journalier)\s+de\s+{_NOMBRE}\s*Euros?"
    rf"(?:\s+à\s+{_NOMBRE}\s*Euros?)?(?:\s+sur\s+(?P<mois>\d+(?:[.,]\d+)?)\s+mois)?",
    re.IGNORECASE,
)
# Bornes de plausibilité du brut annuel temps plein ; au-delà c'est presque toujours une erreur de saisie
MINI, MAXI = 8_000, 400_000


def lire(libelle: str | None) -> tuple[float | None, float | None, str | None]:
    """(min, max) en brut annuel et la période d'origine ; None si le texte n'est pas un montant exploitable."""
    if not libelle:
        return None, None, None
    m = _MOTIF.match(libelle.strip())
    if not m:
        return None, None, None
    periode = m.group("periode").capitalize()
    bas = float(m.group(2).replace(",", "."))
    haut = float(m.group(3).replace(",", ".")) if m.group(3) else bas
    mois = float(m.group("mois").replace(",", ".")) if m.group("mois") else 12.0
    facteur = {
        "Annuel": 1.0,
        "Mensuel": mois,
        "Horaire": HEURES_MOIS * mois,
        "Hebdomadaire": 52.0,
        "Journalier": 218.0,
    }[periode]
    bas, haut = bas * facteur, haut * facteur
    if haut < bas:
        bas, haut = haut, bas
    if not (MINI <= bas <= MAXI and MINI <= haut <= MAXI):
        return None, None, periode
    return round(bas), round(haut), periode


def ajouter(table: pl.DataFrame, colonne: str = "salaire_libelle") -> pl.DataFrame:
    """Ajoute salaire_min, salaire_max, salaire_milieu (brut annuel, €) et salaire_periode."""
    lus = [lire(v) for v in table[colonne].to_list()]
    return table.with_columns(
        pl.Series("salaire_min", [x[0] for x in lus], dtype=pl.Float64),
        pl.Series("salaire_max", [x[1] for x in lus], dtype=pl.Float64),
        pl.Series("salaire_periode", [x[2] for x in lus], dtype=pl.Utf8),
    ).with_columns(((pl.col("salaire_min") + pl.col("salaire_max")) / 2).alias("salaire_milieu"))
