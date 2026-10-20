from datetime import date

import polars as pl

from offres import csp


def brut(**surcharges):
    ligne = {
        "Référence": "O1", "Versant": "Fonction Publique Territoriale", "Métier": "Data Scientist",
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
