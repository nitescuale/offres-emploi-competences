import polars as pl

from offres import salaire


def test_formats_courants():
    assert salaire.lire("Annuel de 35000.0 Euros à 45000.0 Euros sur 12 mois") == (35000, 45000, "Annuel")
    assert salaire.lire("Mensuel de 2000.0 Euros sur 13 mois") == (26000, 26000, "Mensuel")
    bas, haut, periode = salaire.lire("Horaire de 11.88 Euros sur 12 mois")
    assert periode == "Horaire" and 21_000 < bas == haut < 22_000
    assert salaire.lire("Mensuel de 1801,80 Euros") == (21622, 21622, "Mensuel")


def test_textes_inexploitables():
    assert salaire.lire(None) == (None, None, None)
    assert salaire.lire("Selon profil") == (None, None, None)
    assert salaire.lire("Mensuel de 2.0 Euros sur 12 mois") == (None, None, "Mensuel")


def test_ajouter():
    t = salaire.ajouter(pl.DataFrame({"salaire_libelle": ["Annuel de 40000 Euros à 50000 Euros sur 12 mois", None]}))
    assert t["salaire_milieu"].to_list() == [45000, None]
