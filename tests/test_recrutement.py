import polars as pl

from offres import recrutement


def _offres(lignes):
    base = {"organisme": "CHU", "metier": "Infirmier", "intitule": "Infirmier de nuit", "departement": "44",
            "competences_texte": None}
    rows = [{**base, **l} for l in lignes]
    return pl.DataFrame(rows).with_columns(pl.col("date_publication").str.to_date())


def test_republications():
    offres = _offres([
        {"annonce_id": 1, "date_publication": "2023-01-01"},
        {"annonce_id": 2, "date_publication": "2023-03-01"},   # revient 59 jours après : 1 est republiée
        {"annonce_id": 3, "date_publication": "2023-03-03"},   # 2 jours après 2 : trop tôt, doublon plutôt que relance
        {"annonce_id": 4, "date_publication": "2023-01-01", "intitule": "Infirmier (de jour)"},  # autre poste
        {"annonce_id": 5, "date_publication": "2024-06-01", "departement": "85"},  # sert de fin de fichier
    ])
    a = recrutement.republications(offres)
    r = dict(zip(a["annonce_id"], a["republiee"]))
    assert r == {1: True, 2: False, 3: False, 4: False}  # 5 trop récente pour savoir : écartée
    d = dict(zip(a["annonce_id"], a["deja_republiee"]))
    assert d[2] and not d[1] and not d[3]
    assert dict(zip(a["annonce_id"], a["publications_avant"])) == {1: 0, 2: 1, 3: 2, 4: 0}


def test_intitule_norme_et_fenetre():
    offres = _offres([
        {"annonce_id": 1, "date_publication": "2023-01-01", "intitule": "Infirmier DE NUIT !"},
        {"annonce_id": 2, "date_publication": "2023-08-01"},   # 212 jours : au-delà de la fenêtre
        {"annonce_id": 3, "date_publication": "2024-06-01", "departement": "85"},
    ])
    a = recrutement.republications(offres)
    assert a.filter(pl.col("annonce_id") == 1)["intitule_norme"][0] == "infirmier de nuit"
    assert not a.filter(pl.col("annonce_id") == 1)["republiee"][0]
    # Avec une fenêtre plus large, la relance à 212 jours compte
    assert recrutement.republications(offres, max_jours=250).filter(pl.col("annonce_id") == 1)["republiee"][0]
