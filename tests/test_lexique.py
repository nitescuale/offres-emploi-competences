from offres import lexique


def test_extraction_offre_data():
    texte = ("Data analyst H/F : vous maîtrisez SQL et Python (pandas), Power BI ou Tableau. "
             "Connaissance d'AWS appréciée, anglais courant. Méthode Agile.")
    trouve = lexique.extraire(texte)
    for attendu in ["SQL", "Python", "pandas", "Power BI", "Tableau", "AWS", "Anglais", "Agile / Scrum"]:
        assert attendu in trouve
    assert "Java" not in trouve


def test_pas_de_faux_positifs_courants():
    texte = ("Société SAS au capital de 10 000 €, station Shell à Dax. Vous êtes sage-femme, "
             "pose de rails, sas de décontamination, 500 ml, tableau de bord, réactif et javanais.")
    trouve = lexique.extraire(texte)
    assert trouve == [], trouve


def test_langage_r_en_contexte():
    assert "R" in lexique.extraire("Maîtrise de Python ou R pour la modélisation")
    assert "R" not in lexique.extraire("Rez-de-chaussée, bâtiment R")
    assert "JavaScript" in lexique.extraire("Développeur Javascript") and "Java" not in lexique.extraire("Développeur Javascript")
