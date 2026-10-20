"""Collecte des offres : découpage de la période de création en tranches de moins de 1 150 offres, puis pagination.

L'API ne renvoie jamais plus de 1 150 offres pour une même requête. On coupe donc la période en deux tant qu'une
tranche dépasse ce plafond (bissection sur minCreationDate / maxCreationDate). Quand une tranche très courte reste
trop pleine (offres importées en masse à la même seconde), on la découpe encore par type de contrat.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import polars as pl

from offres.api import PLAFOND, TAILLE_PAGE, Client, format_date

DUREE_MIN = timedelta(minutes=1)
TYPES_CONTRAT = ["CDI", "CDD", "MIS", "SAI", "LIB", "FRA", "REP", "CCE", "CPE", "DDI", "DIN", "TTI", "DDT"]


def _pages(client: Client, criteres: dict, premiere: list[dict], total: int) -> Iterator[dict]:
    yield from premiere
    for debut in range(TAILLE_PAGE, min(total, PLAFOND), TAILLE_PAGE):
        page, _ = client.chercher(criteres, debut, min(debut + TAILLE_PAGE, PLAFOND) - 1)
        yield from page


def offres_periode(client: Client, debut: datetime, fin: datetime, criteres: dict | None = None,
                   journal: list | None = None) -> Iterator[dict]:
    """Toutes les offres créées dans [debut, fin], en découpant autant que nécessaire."""
    criteres = dict(criteres or {})
    fenetre = {**criteres, "minCreationDate": format_date(debut), "maxCreationDate": format_date(fin), "sort": 1}
    premiere, total = client.chercher(fenetre)
    if total == 0:
        return
    if total <= PLAFOND:
        if journal is not None:
            journal.append({"debut": debut, "fin": fin, "criteres": json.dumps(criteres), "total": total, "tronque": False})
        yield from _pages(client, fenetre, premiere, total)
        return
    if fin - debut > DUREE_MIN:
        milieu = debut + (fin - debut) / 2
        milieu = milieu.replace(microsecond=0)
        yield from offres_periode(client, debut, milieu, criteres, journal)
        # Les bornes de l'API sont inclusives à la seconde : la seconde moitié commence une seconde plus tard
        yield from offres_periode(client, milieu + timedelta(seconds=1), fin, criteres, journal)
        return
    if "typeContrat" not in criteres:
        for contrat in TYPES_CONTRAT:
            yield from offres_periode(client, debut, fin, {**criteres, "typeContrat": contrat}, journal)
        return
    # Dernier recours : on garde les 1 150 premières et on le signale
    print(f"  ⚠ tranche {format_date(debut)} -> {format_date(fin)} {criteres} : {total} offres, tronquée à {PLAFOND}")
    if journal is not None:
        journal.append({"debut": debut, "fin": fin, "criteres": json.dumps(criteres), "total": total, "tronque": True})
    yield from _pages(client, fenetre, premiere, total)


def _liste(offre: dict, cle: str) -> str | None:
    valeur = offre.get(cle)
    return json.dumps(valeur, ensure_ascii=False) if valeur else None


def aplatir(offre: dict) -> dict:
    """Une offre de l'API -> une ligne à colonnes fixes ; les listes (compétences, formations...) restent en JSON."""
    lieu = offre.get("lieuTravail") or {}
    entreprise = offre.get("entreprise") or {}
    salaire = offre.get("salaire") or {}
    origine = offre.get("origineOffre") or {}
    contexte = offre.get("contexteTravail") or {}
    return {
        "id": offre.get("id"),
        "intitule": offre.get("intitule"),
        "description": offre.get("description"),
        "date_creation": offre.get("dateCreation"),
        "date_actualisation": offre.get("dateActualisation"),
        "lieu_libelle": lieu.get("libelle"),
        "commune": lieu.get("commune"),
        "code_postal": lieu.get("codePostal"),
        "latitude": lieu.get("latitude"),
        "longitude": lieu.get("longitude"),
        "rome_code": offre.get("romeCode"),
        "rome_libelle": offre.get("romeLibelle"),
        "appellation": offre.get("appellationlibelle"),
        "entreprise_nom": entreprise.get("nom"),
        "entreprise_adaptee": entreprise.get("entrepriseAdaptee"),
        "type_contrat": offre.get("typeContrat"),
        "type_contrat_libelle": offre.get("typeContratLibelle"),
        "nature_contrat": offre.get("natureContrat"),
        "experience_exige": offre.get("experienceExige"),
        "experience_libelle": offre.get("experienceLibelle"),
        "salaire_libelle": salaire.get("libelle"),
        "salaire_commentaire": salaire.get("commentaire"),
        "salaire_complements": _liste(salaire, "listeComplements"),
        "duree_travail": offre.get("dureeTravailLibelle"),
        "duree_travail_converti": offre.get("dureeTravailLibelleConverti"),
        "alternance": offre.get("alternance"),
        "nombre_postes": offre.get("nombrePostes"),
        "qualification_code": offre.get("qualificationCode"),
        "qualification_libelle": offre.get("qualificationLibelle"),
        "code_naf": offre.get("codeNAF"),
        "secteur_activite": offre.get("secteurActivite"),
        "secteur_activite_libelle": offre.get("secteurActiviteLibelle"),
        "tranche_effectif": offre.get("trancheEffectifEtab"),
        "origine": origine.get("origine"),
        "partenaires": _liste(origine, "partenaires"),
        "manque_candidats": offre.get("offresManqueCandidats"),
        "accessible_th": offre.get("accessibleTH"),
        "deplacement": offre.get("deplacementLibelle"),
        "competences": _liste(offre, "competences"),
        "qualites_professionnelles": _liste(offre, "qualitesProfessionnelles"),
        "formations": _liste(offre, "formations"),
        "langues": _liste(offre, "langues"),
        "permis": _liste(offre, "permis"),
        "outils_bureautiques": _liste(offre, "outilsBureautiques"),
        "horaires": _liste(contexte, "horaires"),
        "conditions_exercice": _liste(contexte, "conditionsExercice"),
    }


SCHEMA = {
    "id": pl.Utf8, "intitule": pl.Utf8, "description": pl.Utf8, "date_creation": pl.Utf8, "date_actualisation": pl.Utf8,
    "lieu_libelle": pl.Utf8, "commune": pl.Utf8, "code_postal": pl.Utf8, "latitude": pl.Float64, "longitude": pl.Float64,
    "rome_code": pl.Utf8, "rome_libelle": pl.Utf8, "appellation": pl.Utf8, "entreprise_nom": pl.Utf8,
    "entreprise_adaptee": pl.Boolean, "type_contrat": pl.Utf8, "type_contrat_libelle": pl.Utf8, "nature_contrat": pl.Utf8,
    "experience_exige": pl.Utf8, "experience_libelle": pl.Utf8, "salaire_libelle": pl.Utf8, "salaire_commentaire": pl.Utf8,
    "salaire_complements": pl.Utf8, "duree_travail": pl.Utf8, "duree_travail_converti": pl.Utf8, "alternance": pl.Boolean,
    "nombre_postes": pl.Int32, "qualification_code": pl.Utf8, "qualification_libelle": pl.Utf8, "code_naf": pl.Utf8,
    "secteur_activite": pl.Utf8, "secteur_activite_libelle": pl.Utf8, "tranche_effectif": pl.Utf8, "origine": pl.Utf8,
    "partenaires": pl.Utf8, "manque_candidats": pl.Boolean, "accessible_th": pl.Boolean, "deplacement": pl.Utf8,
    "competences": pl.Utf8, "qualites_professionnelles": pl.Utf8, "formations": pl.Utf8, "langues": pl.Utf8,
    "permis": pl.Utf8, "outils_bureautiques": pl.Utf8, "horaires": pl.Utf8, "conditions_exercice": pl.Utf8,
}


def en_table(offres: list[dict], vue_le: datetime) -> pl.DataFrame:
    lignes = [aplatir(o) for o in offres]
    for ligne in lignes:
        # Certains champs arrivent tantôt en nombre, tantôt en texte
        for cle in ("origine", "code_postal", "commune", "secteur_activite", "tranche_effectif"):
            if ligne[cle] is not None:
                ligne[cle] = str(ligne[cle])
    table = pl.DataFrame(lignes, schema=SCHEMA, orient="row") if lignes else pl.DataFrame(schema=SCHEMA)
    table = (
        table.with_columns(
            pl.col("date_creation").str.to_datetime(time_zone="UTC", strict=False),
            pl.col("date_actualisation").str.to_datetime(time_zone="UTC", strict=False),
            pl.lit(vue_le).alias("vue_le"),
        )
        # Une offre peut tomber dans deux tranches si elle est actualisée pendant la collecte
        .unique("id", keep="last", maintain_order=True)
    )
    return table


def mettre_a_jour_index(index: pl.DataFrame | None, offres: pl.DataFrame, vue_le: datetime, complet: bool) -> pl.DataFrame:
    """Index de toutes les offres déjà vues : première et dernière apparition, pour mesurer la durée de vie.

    `complet` indique une photo de tout le stock : seules ces photos permettent de dire qu'une offre a disparu.
    """
    vues = offres.select(
        "id", "date_creation", "date_actualisation", pl.lit(vue_le).alias("premiere_vue"), pl.lit(vue_le).alias("derniere_vue"),
    )
    if index is None or index.is_empty():
        nouveau = vues
    else:
        nouveau = (
            pl.concat([index.select(vues.columns), vues], how="vertical_relaxed")
            .group_by("id")
            .agg(
                pl.col("date_creation").min(),
                pl.col("date_actualisation").max(),
                pl.col("premiere_vue").min(),
                pl.col("derniere_vue").max(),
            )
        )
    if complet:
        nouveau = nouveau.with_columns((pl.col("derniere_vue") == vue_le).alias("en_ligne"))
    elif index is not None and "en_ligne" in index.columns:
        nouveau = nouveau.join(index.select("id", "en_ligne"), on="id", how="left").with_columns(
            pl.col("en_ligne").fill_null(True)
        )
    else:
        nouveau = nouveau.with_columns(pl.lit(True).alias("en_ligne"))
    return nouveau.sort("premiere_vue", "id")


def maintenant() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)
