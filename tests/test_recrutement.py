import math

import polars as pl

from offres import recrutement


def _offres(lignes):
    base = {"organisme": "CHU", "metier": "Infirmier", "intitule": "Infirmier de nuit", "departement": "44",
            "competences_texte": None, "reference": "r"}
    rows = [{**base, **l} for l in lignes]
    fin = {**base, "annonce_id": 999, "date_publication": "2026-01-01", "departement": "85"}  # fixe la fin du fichier
    return pl.DataFrame(rows + [fin]).with_columns(pl.col("date_publication").str.to_date())


def _par_id(a, col):
    return dict(zip(a["annonce_id"], a[col]))


def test_republications():
    a = recrutement.republications(_offres([
        {"annonce_id": 1, "date_publication": "2023-01-01"},
        {"annonce_id": 2, "date_publication": "2023-03-01"},   # revient 59 jours après : 1 est republiée
        {"annonce_id": 3, "date_publication": "2023-03-03"},   # 2 jours après 2 : doublon, pas une relance
        {"annonce_id": 4, "date_publication": "2023-01-01", "intitule": "Infirmier (de jour)"},  # autre poste
    ]))
    assert _par_id(a, "republiee") == {1: True, 2: False, 3: False, 4: False}  # 999 trop récente : écartée
    d = _par_id(a, "deja_republiee")
    assert d[2] and d[3] and not d[1] and not d[4]
    assert _par_id(a, "publications_an") == {1: 0, 2: 1, 3: 2, 4: 0}


def test_doublon_puis_relance():
    # Un doublon 2 jours après ne masque pas la vraie relance qui suit
    a = recrutement.republications(_offres([
        {"annonce_id": 1, "date_publication": "2023-01-01"},
        {"annonce_id": 2, "date_publication": "2023-01-03"},
        {"annonce_id": 3, "date_publication": "2023-03-01"},
    ]))
    assert _par_id(a, "republiee") == {1: True, 2: True, 3: False}
    assert _par_id(a, "deja_republiee") == {1: False, 2: False, 3: True}


def test_bornes_de_la_fenetre():
    a = recrutement.republications(_offres([
        {"annonce_id": 1, "date_publication": "2023-01-01"},
        {"annonce_id": 2, "date_publication": "2023-01-08"},   # 7 jours : compte
        {"annonce_id": 3, "date_publication": "2023-07-07"},   # 180 jours après 2 : compte
        {"annonce_id": 4, "date_publication": "2024-01-04"},   # 181 jours après 3 : ne compte pas
    ]))
    assert _par_id(a, "republiee") == {1: True, 2: True, 3: False, 4: False}
    # Une fenêtre plus large compte la relance à 181 jours
    assert _par_id(recrutement.republications(_offres([
        {"annonce_id": 3, "date_publication": "2023-07-07"},
        {"annonce_id": 4, "date_publication": "2024-01-04"},
    ]), max_jours=200), "republiee")[3]


def test_meme_jour_et_historique_glissant():
    a = recrutement.republications(_offres([
        {"annonce_id": 1, "date_publication": "2023-01-01"},
        {"annonce_id": 2, "date_publication": "2023-01-01"},   # même jour : ne compte pas dans l'historique de 1
        {"annonce_id": 3, "date_publication": "2023-06-01"},
        {"annonce_id": 4, "date_publication": "2024-05-01"},   # 1/1/2023 sorti de la fenêtre d'un an
    ]))
    assert _par_id(a, "publications_an") == {1: 0, 2: 0, 3: 2, 4: 1}
    assert _par_id(a, "republiee")[1] and _par_id(a, "republiee")[2]


def test_censure_et_cles_manquantes():
    offres = _offres([
        {"annonce_id": 1, "date_publication": "2025-07-05"},   # fin (2026-01-01) - 180 jours : gardée
        {"annonce_id": 2, "date_publication": "2025-07-06"},   # trop récente : écartée
        {"annonce_id": 3, "date_publication": "2023-01-01", "departement": None},
        {"annonce_id": 4, "date_publication": "2023-02-01", "departement": None},
    ])
    a = recrutement.republications(offres)
    assert set(a["annonce_id"]) == {1}


def test_variables_et_aligner():
    a = recrutement.republications(_offres([
        {"annonce_id": 1, "date_publication": "2023-01-01", "teletravail": True, "management": None},
        {"annonce_id": 2, "date_publication": "2023-03-01", "teletravail": None, "management": False},
    ]).with_columns(versant=pl.lit("FPH"), categorie=pl.lit("A"), nature_emploi=pl.lit("x"), statut_poste=pl.lit("Vacant"),
                    experience=pl.lit(None, pl.Utf8), temps_plein=pl.lit(True), niveau_etudes=pl.lit(6),
                    postes_annonce=pl.lit(1)))
    x = recrutement.variables(a)
    assert list(x.columns) == recrutement.CATEGORIELLES + recrutement.NUMERIQUES
    assert str(x["metier"].dtype) == "category" and x["teletravail"].tolist()[0] == 1.0
    assert math.isnan(x["teletravail"].tolist()[1])
    autre = x.copy()
    autre["metier"] = autre["metier"].astype(str).replace("Infirmier", "Sage-femme").astype("category")
    aligne = recrutement.aligner(autre, x)
    assert aligne["metier"].isna().all() and list(aligne["metier"].cat.categories) == ["Infirmier"]
