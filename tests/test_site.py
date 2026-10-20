import json
import shutil
import subprocess
from pathlib import Path

import polars as pl
import pytest

from offres import competences, web

RACINE = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")

TEXTES = [
    "﻿Niveau d'étude ou de diplôme : Doctorat\nMédecin du sport",
    "Savoir-être : rigueur, autonomie, esprit d'équipe, curiosité",
    "- Bonne connaissance de l'environnement territorial\n- Maîtrise des outils bureautiques (indispensable)",
    "• Management : expertise\n• Capacité à travailler en équipe ; Sens du service public",
    " Connaissances juridiques\n1) Rédaction d'actes\na) Cf. fiche de poste",
    "Compétences techniques :\nPython, R, SQL\nUn budget de 1,5 million d'euros, à suivre avec rigueur",
    "Être capable de conduire un projet, de l'animer et d'en rendre compte auprès de la hiérarchie et des partenaires",
    "Œuvrer pour la qualité ; niveau B2 en anglais : souhaité",
]


def _node(script: str, entree: dict) -> dict:
    module = (RACINE / "site" / "js" / "extraction.js").as_uri()
    code = (f"import * as x from {json.dumps(module)};\nimport {{ readFileSync }} from 'node:fs';\n"
            f"const entree = JSON.parse(readFileSync(0, 'utf8'));\n{script}")
    r = subprocess.run([NODE, "--input-type=module", "-e", code], input=json.dumps(entree), capture_output=True,
                       text=True, check=True)
    return json.loads(r.stdout)


@pytest.mark.skipif(NODE is None, reason="Node.js absent")
def test_extraction_js_identique_a_python():
    attendu = [[[i, competences.normaliser(i)] for i in competences.segmenter(t)] for t in TEXTES]
    obtenu = _node("console.log(JSON.stringify(entree.map((t) => x.segmenter(t).map((i) => [i, x.normaliser(i)]))));", TEXTES)
    assert obtenu == attendu
    assert any(len(items) > 1 for items in attendu)  # les textes exercent bien le découpage


@pytest.mark.skipif(NODE is None, reason="Node.js absent")
def test_extraction_js_sur_un_echantillon_du_corpus():
    textes = json.loads((RACINE / "tests" / "donnees" / "textes_competences.json").read_text())["textes"]
    attendu = [[[i, competences.normaliser(i)] for i in competences.segmenter(t)] for t in textes]
    obtenu = _node("console.log(JSON.stringify(entree.map((t) => x.segmenter(t).map((i) => [i, x.normaliser(i)]))));", textes)
    differents = [t for t, a, o in zip(textes, attendu, obtenu) if a != o]
    assert not differents, differents[:3]


@pytest.mark.skipif(NODE is None, reason="Node.js absent")
def test_tfidf_js_identique_a_scikit_learn():
    libelles = ["Travail en équipe", "Travailler en équipe pluridisciplinaire", "Analyse statistique des données",
                "Programmation en Python", "Gestion administrative du personnel", "Rédaction d'actes administratifs",
                "Esprit d'équipe", "Statistiques", "Conduite de projet", "Animer une réunion", "a", "Utiliser R"]
    catalogue = pl.DataFrame({"code_ogr": [str(i) for i in range(len(libelles))], "libelle": libelles}).with_columns(
        forme=pl.col("libelle").map_elements(competences.normaliser, return_dtype=pl.Utf8))
    requetes = ["travail d'équipe", "analyse de données statistiques", "python", "gestion du personnel",
                "rédiger des actes", "conduire un projet", "r"]
    formes = [competences.normaliser(q) for q in requetes]
    attendu = competences.Rapprocheur(catalogue, "tfidf").candidats(requetes, k=3)
    obtenu = _node("const t = new x.Tfidf(entree.catalogue);"
                   "console.log(JSON.stringify(entree.formes.map((f) => t.chercher(f, 3))));",
                   {"catalogue": catalogue["forme"].to_list(), "formes": formes})
    for a, o in zip(attendu, obtenu):
        a = [(i, s) for i, s in a if s > 0]  # scikit-learn complète par des entrées de score nul, pas le JavaScript
        assert [i for i, _ in a] == [i for i, _ in o]
        assert [s for _, s in a] == pytest.approx([s for _, s in o], abs=1e-5)


def test_territoires_et_carte():
    t = web.territoires()
    assert len(t["departements"]) == 96 + 11 and t["departements"]["29"]["region"] == "Bretagne"
    carte = json.loads((RACINE / "site" / "geo" / "departements.json").read_text())
    assert set(carte["departements"]) == set(web.CONNUS) - set(web.OUTRE_MER)


def _jeu():
    """Deux métiers, deux départements ; le poste d'infirmier à Nantes est republié 60 jours plus tard."""
    lignes = [
        # id, date, métier, département, télétravail, catégorie, management, texte
        (1, "2023-01-10", "Infirmier", "44", None, "A", False, "Travail en équipe\nSoins infirmiers"),
        (2, "2023-03-11", "Infirmier", "44", None, "A", False, None),
        (3, "2023-02-01", "Infirmier", "75", True, "A", True, "Travail en équipe"),
        (4, "2024-05-01", "Agent d'accueil", "75", False, "C", None, None),
        (5, "2024-06-01", "Agent d'accueil", "99", None, "C", None, None),
        (6, "2025-09-30", "Agent d'accueil", "75", None, None, None, None),  # fixe la fin du fichier
    ]
    offres = pl.DataFrame(lignes, schema=["annonce_id", "date_publication", "metier", "departement", "teletravail",
                                          "categorie", "management", "competences_texte"], orient="row")
    offres = offres.with_columns(pl.col("date_publication").str.to_date(), reference=pl.col("annonce_id").cast(pl.Utf8),
                                 organisme=pl.lit("CHU"), intitule=pl.col("metier"))
    items = competences.items_des_offres(offres).select("annonce_id", "forme")
    formes = pl.DataFrame({"forme": ["travail en equipe", "soins infirmiers"], "code_ogr": ["10", "20"], "occurrences": [2, 1]})
    catalogue = pl.DataFrame({"code_ogr": ["10", "20"], "libelle": ["Travail en équipe", "Réaliser des soins"],
                              "type": ["Savoir", "Savoir-faire"], "sous_type": ["Domaines d'expertise", None],
                              "domaine_competence": [None, "Management, Social, Soin"],
                              "libelle_macro_competence": [None, "Soigner"]})
    metiers_rome = pl.DataFrame({"metier": ["Infirmier"], "offres": [3], "code_rome": ["J1506"], "libelle_rome": ["Soins infirmiers"],
                                 "appellation": ["Infirmier / Infirmière"]})
    par_fiche = pl.DataFrame({"code_rome": ["J1506", "J1506"], "code_ogr": ["20", "10"], "coeur": [True, False]})
    return offres, formes, items, metiers_rome, catalogue, par_fiche


def test_donnees_tableau(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "MIN_TEXTES", 1)
    offres, formes, items, metiers_rome, catalogue, par_fiche = _jeu()
    resume = web.donnees_tableau(tmp_path, offres, formes, items, metiers_rome, catalogue, par_fiche)
    assert resume["offres"] == 6 and resume["metiers"] == 2 and resume["textes"] == 2
    assert resume["nb_mois"] == 45  # janvier 2022 à septembre 2025 (la fin du mois est presque atteinte)

    metiers = json.loads((tmp_path / "metiers.json").read_text())
    accueil, infirmier = web.identifiant("Agent d'accueil"), web.identifiant("Infirmier")
    assert [m[:3] for m in metiers["lignes"]] == [[accueil, "Agent d'accueil", 3], [infirmier, "Infirmier", 3]]
    inf = json.loads((tmp_path / "metiers" / f"{infirmier}.json").read_text())
    k = dict(zip(resume["colonnes_kpi"], inf["territoires"]["44"]["annees"]["2023"]))
    assert k["n"] == 2 and k["tt_r"] == 0 and k["cat_A"] == 2 and k["mg_r"] == 2
    assert (k["rep"], k["rep_r"]) == (1, 2)  # l'annonce 1 revient 60 jours plus tard ; la 2, non
    assert inf["territoires"]["44"]["serie"][12] == 1 and inf["territoires"]["44"]["serie"][14] == 1
    assert inf["competences"]["liste"][0] == ["Travail en équipe", "Savoirs · Domaines d'expertise", 1.0]
    assert inf["fiche"]["code_rome"] == "J1506" and inf["fiche"]["coeur"] == ["Réaliser des soins"]

    tous = json.loads((tmp_path / "metiers" / "tous.json").read_text())
    assert "?" in tous["territoires"]  # département 99 : compté dans la France entière, pas sur la carte
    assert sum(sum(t["serie"]) for t in tous["territoires"].values()) == 6
    frequents = tous["metiers_frequents"]
    assert sorted(frequents["France|toutes"]) == sorted([[accueil, 3], [infirmier, 3]])
    assert frequents["r:Pays de la Loire|2023"] == [[infirmier, 2]]
    assert frequents["75|2024"] == [[accueil, 1]]
    assert web.identifiant("Infirmier") == infirmier  # stable d'une construction à l'autre


def test_donnees_outil(tmp_path):
    _, formes, items, metiers_rome, catalogue, par_fiche = _jeu()
    metiers = pl.DataFrame({"id": ["abc"], "metier": ["Infirmier"]})
    web.donnees_outil(tmp_path, formes, items, catalogue, par_fiche, metiers_rome, metiers,
                      noms_fiches={"J1506": "Soins infirmiers"})
    cat = json.loads((tmp_path / "catalogue.json").read_text())
    assert cat["libelles"] == ["Travail en équipe", "Réaliser des soins"]
    assert [cat["domaines"][d] for d in cat["domaine"]] == ["Savoirs · Domaines d'expertise", "Management, Social, Soin"]
    assert cat["transversales"] == [0, 1]  # citées par 2 et 1 des 2 annonces avec texte, au-dessus de 5 %
    vues = json.loads((tmp_path / "formes.json").read_text())
    assert vues == {"formes": ["travail en equipe"], "entrees": [0], "occurrences": [2]}  # vue une seule fois : écartée
    fiches = json.loads((tmp_path / "fiches.json").read_text())
    assert fiches["lignes"] == [["J1506", "Soins infirmiers", [1], [0], [["abc", "Infirmier"]]]]
