import math

import polars as pl
import pytest

from offres import structure

METIERS = {
    "comptable": ("comptabilite publique", "budget"),
    "soignant": ("hygiene hospitaliere", "soins"),
    "cuisinier": ("techniques culinaires", "hygiene alimentaire"),
    "archiviste": ("archivage", "gestion des collections"),
    "acheteur": ("marches publics", "negociation"),
}


def _donnees():
    # Cinq métiers, chacun avec ses deux compétences propres, et « rigueur » partout
    lignes = [(f"{m}{i}", m, f) for m, propres in METIERS.items() for i in range(60) for f in ("rigueur", *propres)]
    # Restes de rubriques, à écarter
    lignes += [("comptable0", "comptable", f) for f in ("competences", "connaissances et experiences souhaitables",
                                                         "experiences professionnelles anterieures", "competence outil")]
    items = pl.DataFrame(lignes, schema=["annonce_id", "metier", "forme"], orient="row")
    offres = items.unique("annonce_id").select("annonce_id", "metier").with_columns(competences_texte=pl.lit("texte"))
    return items.select("annonce_id", "forme"), offres


def test_items_par_metier_et_transversalite():
    items, offres = _donnees()
    x = structure.items_par_metier(items, offres, min_annonces=20)
    assert not {"competences", "connaissances et experiences souhaitables", "experiences professionnelles anterieures",
                "competence outil"} & set(x["forme"].to_list())
    t = structure.transversalite(x)
    assert dict(zip(t["forme"], t["transversale"]))["rigueur"]
    assert not dict(zip(t["forme"], t["transversale"]))["budget"]


def test_cooccurrences_et_communautes():
    items, offres = _donnees()
    x = structure.items_par_metier(items, offres)
    paires = structure.cooccurrences(x, ["comptabilite publique", "budget", "hygiene hospitaliere", "soins", "rigueur"])
    npmi = {(a, b): v for a, b, v in paires.select("a", "b", "npmi").iter_rows()}
    assert npmi[("budget", "comptabilite publique")] > 0.9
    # « rigueur » est partout : citée avec « budget » ni plus ni moins que par hasard
    assert abs(npmi[("budget", "rigueur")]) < 0.05
    _, groupes = structure.communautes(paires, seuil_npmi=0.5)
    assert {"budget", "comptabilite publique"} in groupes and {"hygiene hospitaliere", "soins"} in groupes


@pytest.mark.filterwarnings("ignore:invalid value encountered in sqrt")  # NMF aléatoire sur un jeu jouet
def test_familles():
    items, offres = _donnees()
    metiers, vocab, m = structure.matrice_metiers(structure.items_par_metier(items, offres))
    assert metiers == sorted(METIERS) and "rigueur" not in vocab and m.shape == (5, 10)
    w, h = structure.familles(m, k=5)
    # Chaque métier a sa famille, et la famille est portée par ses deux compétences propres
    assert sorted(w.argmax(axis=1).tolist()) == [0, 1, 2, 3, 4]
    famille = w[metiers.index("soignant")].argmax()
    assert {vocab[j] for j in h[famille].argsort()[-2:]} == {"hygiene hospitaliere", "soins"}
    stab = structure.stabilite(m, [3, 5], graines=3)
    assert stab["k"].to_list() == [3, 5] and stab["ari_min"].le(stab["ari_moyen"]).all() and stab["ari_moyen"].le(1).all()


def test_transversalite_part_minimale():
    # « tableur » est citée une fois dans chaque métier : pas assez pour être transversale
    items, offres = _donnees()
    items = items.vstack(pl.DataFrame({"annonce_id": [f"{m}0" for m in METIERS], "forme": ["tableur"] * 5}))
    t = structure.transversalite(structure.items_par_metier(items, offres))
    ligne = t.filter(pl.col("forme") == "tableur").row(0, named=True)
    assert ligne["annonces"] == 5 and ligne["metiers"] == 0 and not ligne["transversale"]
    assert structure.transversalite(structure.items_par_metier(items, offres), part_min=0)["transversale"].sum() == 2


def test_npmi_valeur_exacte():
    # 4 annonces : a et b ensemble dans 2, a seule dans 1, b absente ailleurs
    x = pl.DataFrame({"annonce_id": ["1", "1", "2", "2", "3", "4"], "forme": ["a", "b", "a", "b", "a", "c"],
                      "metier": ["m"] * 6})
    npmi = structure.cooccurrences(x, ["a", "b"], min_paires=1)["npmi"][0]
    p_ab, p_a, p_b = 2 / 4, 3 / 4, 2 / 4
    assert math.isclose(npmi, math.log(p_ab / (p_a * p_b)) / -math.log(p_ab))


def test_metier_sans_vocabulaire_ecarte():
    items, offres = _donnees()
    # Un sixième métier qui ne cite que « rigueur » (transversale) : il n'a pas de ligne dans la matrice
    extra = pl.DataFrame({"annonce_id": [f"greffier{i}" for i in range(30)], "forme": ["rigueur"] * 30})
    offres = offres.vstack(extra.select("annonce_id").with_columns(metier=pl.lit("greffier"), competences_texte=pl.lit("t")))
    metiers, _, m = structure.matrice_metiers(structure.items_par_metier(items.vstack(extra), offres))
    assert "greffier" not in metiers and m.shape[0] == 5
