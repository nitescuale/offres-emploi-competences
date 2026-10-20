import polars as pl

from offres.competences import Rapprocheur, normaliser, segmenter


def test_segmenter_puces_et_titres():
    texte = "Savoirs\r\n- Connaissance de l'organisation ;\r\n- C++ ; o Rigueur\n1) Python\n* SQL"
    assert segmenter(texte) == ["Connaissance de l'organisation", "C++", "Rigueur", "Python", "SQL"]


def test_segmenter_puces_wingdings():
    texte = "Compétences :\r\n\tCompétences techniques en sérologie \r\n\tForce de proposition"
    assert segmenter(texte) == ["Compétences techniques en sérologie", "Force de proposition"]
    # Niveau et compétence séparés par une tabulation (tableaux copiés depuis un traitement de texte)
    assert segmenter("Niveau maîtrise requis\tSavoir travailler en équipe") == ["Savoir travailler en équipe"]


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


class FauxModele:
    """Sac de mots normalisé : assez pour vérifier la mécanique des embeddings sans charger de modèle."""

    vocabulaire = ("projet", "gestion", "soudure", "marches", "publics", "equipe")

    def encoder(self, textes, requete=True):
        import numpy as np

        v = np.array([[float(m in normaliser(t)) for m in self.vocabulaire] for t in textes]) + 1e-3
        return v / np.linalg.norm(v, axis=1, keepdims=True)


def test_rapprocheur_hybride():
    catalogue = pl.DataFrame({
        "code_ogr": ["1", "2", "3"],
        "libelle": ["Marchés publics", "Gestion de projet", "Techniques de soudure"],
    }).with_columns(pl.col("libelle").map_elements(normaliser, return_dtype=pl.Utf8).alias("forme"))
    r = Rapprocheur(catalogue, "hybride", FauxModele())
    assert r.rapprocher(["Conduite de projets", "soudure à l'arc"])["code_ogr"].to_list() == ["2", "3"]
    cands = r.candidats(["gestion de projet"], k=3)[0]
    assert cands[0][0] == 1 and len(cands) == 3
    assert cands[0][1] >= cands[1][1] >= cands[2][1]


def test_rattacher_formes_reprend_le_cache(monkeypatch):
    from offres import competences

    catalogue = pl.DataFrame({
        "code_ogr": ["1", "2", "3"],
        "libelle": ["Marchés publics", "Gestion de projet", "Techniques de soudure"],
    }).with_columns(pl.col("libelle").map_elements(normaliser, return_dtype=pl.Utf8).alias("forme"))
    monkeypatch.setattr(competences, "catalogue_rome", lambda: catalogue)
    items = pl.DataFrame({"annonce_id": ["a", "b", "b"], "item": ["Gestion de projets", "Soudure", "gestion de projets"]})
    items = items.with_columns(pl.col("item").map_elements(normaliser, return_dtype=pl.Utf8).alias("forme"))
    premier = competences.rattacher_formes(items, FauxModele())
    assert dict(zip(premier["forme"], premier["code_ogr"])) == {"gestion de projets": "2", "soudure": "3"}
    assert premier.filter(pl.col("forme") == "gestion de projets")["occurrences"][0] == 2
    assert premier["candidats"].list.len().to_list() == [3, 3]

    # Une forme déjà rattachée n'est pas recalculée : on le vérifie avec un catalogue qui ne la contient plus
    monkeypatch.setattr(competences, "catalogue_rome", lambda: catalogue.filter(pl.col("code_ogr") != "2"))
    nouveaux = items.vstack(pl.DataFrame({"annonce_id": ["c"], "item": ["Marchés publics"], "forme": ["marches publics"]}))
    second = competences.rattacher_formes(nouveaux, FauxModele(), cache=premier)
    assert dict(zip(second["forme"], second["code_ogr"]))["gestion de projets"] == "2"
    assert dict(zip(second["forme"], second["code_ogr"]))["marches publics"] == "1"
