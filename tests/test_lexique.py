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


def test_corrections_relecture():
    assert "ERP" not in lexique.extraire("Réglementation des ERP (établissements recevant du public), SSIAP 2")
    assert "Intelligence artificielle" not in lexique.extraire("Titulaire du SSIAP, en lien avec l'IA-IPR")
    assert "Agile / Scrum" not in lexique.extraire("Esprit agile et force de proposition")
    assert "Agile / Scrum" in lexique.extraire("Pratique des méthodes agiles")
    assert "Statistiques" not in lexique.extraire("Production de tableaux de bord et statistiques d'activité")
    assert "Statistiques" in lexique.extraire("Maîtrise des méthodes statistiques")
    assert "Oracle" not in lexique.extraire("Administration Oracle Linux")
    trouve = lexique.extraire("Python, C ou Perl ; QGIS ; Outlook ; SPSS")
    for attendu in ["Python", "C", "Perl", "SIG (QGIS, ArcGIS)", "Pack Office", "SPSS / Stata"]:
        assert attendu in trouve, attendu
    assert "Pack Office" not in lexique.extraire("Maîtrise des outils bureautiques")
