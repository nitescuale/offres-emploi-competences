import polars as pl

from offres import familles


def test_metiers_data():
    t = pl.DataFrame({"metier": ["Data Scientist", "Analyste de données RH", "Déléguée / Délégué à la protection des données numériques",
                                 "Enseignante / Enseignant", None]})
    assert t.select(familles.est_data())["metier"].to_list() == [True, True, False, False, False]
