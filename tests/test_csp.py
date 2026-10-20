from datetime import date

import polars as pl

from offres import csp


def brut(**surcharges):
    ligne = {
        "Référence": "O1", "Organisme de rattachement": "Communes", "Versant": "Fonction Publique Territoriale", "Métier": "Data Scientist",
        "Intitulé du poste": "Data scientist (H/F)", "Catégorie": "Catégorie A (cadre)", "Localisation du poste": "Cher (18 )",
        "Niveau d'études": "Niveau 7 Master/diplômes équivalents", "Télétravail": " Oui", "Management": " Non",
        "Temps Plein": "None", "Date de première publication": "01/01/2026", "Compétences attendues": "Python, SQL",
    }
    ligne.update(surcharges)
    return pl.DataFrame([ligne])


def test_normaliser():
    t = csp.normaliser(brut(), "f2026")
    r = t.row(0, named=True)
    assert r["departement"] == "18" and r["departement_nom"] == "Cher"
    assert r["categorie"] == "A" and r["niveau_etudes"] == 7
    assert r["teletravail"] is True and r["management"] is False and r["temps_plein"] is None
    assert r["date_publication"] == date(2026, 1, 1)
    assert r["employeur"] is None  # colonne absente du fichier
    assert csp.normaliser(brut(**{"Localisation du poste": "Corse-du-Sud (2a)"}), "f")["departement"][0] == "2A"
    assert csp.normaliser(brut(**{"Localisation du poste": "Ain (1)"}), "f")["departement"][0] == "01"


def test_consolider_garde_le_fichier_le_plus_recent():
    a = csp.normaliser(brut(**{"Intitulé du poste": "ancien"}), "offres_2025")
    b = csp.normaliser(brut(**{"Intitulé du poste": "nouveau"}), "offres_2026")
    c = csp.normaliser(brut(Référence="O2"), "offres_2025")
    t = csp.consolider([b, a, c])
    assert t.height == 2
    assert t.filter(pl.col("reference") == "O1")["intitule"][0] == "nouveau"


def test_lire_csv_point_virgule_latin1():
    contenu = "Référence;Métier\nO1;Agent d'accueil\n".encode("latin-1")
    t = csp.lire_csv(contenu)
    assert t.columns == ["Référence", "Métier"] and t.height == 1


def test_metier_harmonise():
    t = csp.normaliser(brut(Métier="*Responsable d’un programme  d’études*"), "f")
    assert t["metier"][0] == "Responsable d'un programme d'études"


def test_lignes_eclatees_regroupees_et_versant_deduit():
    lignes = [
        brut(Spécialisation="Droit", Langues="Anglais"),
        brut(Spécialisation="Économie", Langues="Anglais"),
        brut(Référence="O2", Versant=None),
    ]
    t = csp.consolider([csp.normaliser(pl.concat(lignes, how="diagonal_relaxed"), "2026-01-01 f")])
    assert t.height == 2
    o1 = t.filter(pl.col("reference") == "O1").row(0, named=True)
    assert o1["specialisation"] == "Droit | Économie" and o1["langues"] == "Anglais"
    # O2 a le même organisme que O1, qui n'a qu'un versant : on le lui attribue
    assert t.filter(pl.col("reference") == "O2")["versant"][0] == "Fonction Publique Territoriale"


def test_annonces_multipostes():
    t = csp.consolider([csp.normaliser(pl.concat([brut(), brut(Référence="O2"), brut(Référence="O3", Métier="Autre")]), "f")])
    postes = dict(zip(t["reference"], t["postes_annonce"]))
    assert postes == {"O1": 2, "O2": 2, "O3": 1}


def test_dates_aberrantes_et_code_postal():
    t = csp.normaliser(brut(**{"Date de vacance de l'emploi": "31/12/9999", "Localisation du poste": None,
                               "Lieu d'affectation": "Mairie - 20200 Bastia"}), "f")
    assert t["date_vacance"][0] is None
    assert t["departement"][0] == "2B"
    assert csp.normaliser(brut(**{"Localisation du poste": None, "Lieu d'affectation": "97400 Saint-Denis"}), "f")["departement"][0] == "974"
