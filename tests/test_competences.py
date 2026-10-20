import polars as pl

from offres.competences import Rapprocheur, normaliser, segmenter


def test_segmenter_puces_et_titres():
    texte = "Savoirs\r\n- Connaissance de l'organisation ;\r\n- C++ ; o Rigueur\n1) Python\n* SQL"
    assert segmenter(texte) == ["Connaissance de l'organisation", "C++", "Rigueur", "Python", "SQL"]


def test_segmenter_puces_wingdings():
    texte = "Compétences :\r\n\tCompétences techniques en sérologie \r\n\tForce de proposition"
    assert segmenter(texte) == ["Compétences techniques en sérologie", "Force de proposition"]


def test_segmenter_liste_a_virgules():
    assert segmenter("Autonome, Adaptation, Prise d'initiative, Rigueur") == [
        "Autonome", "Adaptation", "Prise d'initiative", "Rigueur",
    ]
    # Une phrase avec virgules reste entière
    phrase = "Capacité à travailler en équipe, en lien avec les partenaires extérieurs et les services de l'État"
    assert segmenter(phrase) == [phrase]


def test_segmenter_niveaux_et_rubriques():
    texte = (
        "Connaissances\n\nNiveau application:\n- Outils de gestion de projet\n\nNiveau maîtrise:\n- Politiques publiques\n"
        "Aide à la décision : expertise\nLogiciels : Excel, Word\nSavoirs théoriques et pratiques :\nCompétences opérationnelles"
    )
    assert segmenter(texte) == ["Outils de gestion de projet", "Politiques publiques", "Aide à la décision", "Excel", "Word"]


def test_segmenter_vide():
    assert segmenter(None) == []
    assert segmenter("cf. fiche de poste") == []


def test_normaliser():
    assert normaliser("Bonne connaissance des marchés publics") == "marches publics"
    assert normaliser("Capacité d'analyse") == "analyse"
    assert normaliser("Maîtrise de soi") == "maitrise de soi"
    assert normaliser("SIG (indispensable)") == "sig"
    assert normaliser("C++ / C#") == "c++ c#"


def test_rapprocheur_dictionnaire_et_tfidf():
    catalogue = pl.DataFrame({
        "code_ogr": ["1", "2", "3"],
        "libelle": ["Marchés publics", "Gestion de projet", "Techniques de soudure"],
    }).with_columns(pl.col("libelle").map_elements(normaliser, return_dtype=pl.Utf8).alias("forme"))
    exact = Rapprocheur(catalogue, "dictionnaire").rapprocher(["Connaissance des marchés publics", "Rigueur"])
    assert exact["code_ogr"].to_list() == ["1", None]
    proche = Rapprocheur(catalogue, "tfidf").rapprocher(["gestion de projets informatiques"])
    assert proche["code_ogr"][0] == "2"
