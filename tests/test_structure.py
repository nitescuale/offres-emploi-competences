import polars as pl

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
    lignes = [(f"{m}{i}", m, f) for m, propres in METIERS.items() for i in range(30) for f in ("rigueur", *propres)]
    lignes += [("comptable0", "comptable", "competences")]  # reste de rubrique, à écarter
    items = pl.DataFrame(lignes, schema=["annonce_id", "metier", "forme"], orient="row")
    offres = items.unique("annonce_id").select("annonce_id", "metier").with_columns(competences_texte=pl.lit("texte"))
    return items.select("annonce_id", "forme"), offres


def test_items_par_metier_et_transversalite():
    items, offres = _donnees()
    x = structure.items_par_metier(items, offres, min_annonces=20)
    assert "competences" not in x["forme"].to_list()
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
