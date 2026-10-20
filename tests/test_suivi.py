from datetime import date, timedelta

import polars as pl
import pytest

from offres import suivi


def _offres(lignes: list[tuple]) -> pl.DataFrame:
    """(date, organisme, texte, métier, département) -> table au format du fichier consolidé."""
    t = pl.DataFrame(lignes, schema=["date_publication", "organisme", "competences_texte", "metier", "departement"], orient="row")
    return t.with_row_index("i").with_columns(
        pl.col("date_publication").cast(pl.Date),
        reference=pl.format("R{}", "i"), annonce_id=pl.col("i").cast(pl.UInt64), categorie=pl.lit("A"),
    ).drop("i")


def _mois(debut: date, n: int) -> list[date]:
    return [date(debut.year + (debut.month - 1 + k) // 12, (debut.month - 1 + k) % 12 + 1, 1) for k in range(n)]


def _regulier(fin: date = date(2025, 6, 26), par_mois: int = 20, texte_armee: bool = True) -> list[tuple]:
    """Offres de janvier 2023 à `fin` ; l'armée écrit des textes, puis plus du tout à partir de 2025 si demandé."""
    lignes = []
    for m in _mois(date(2023, 1, 1), (fin.year - 2023) * 12 + fin.month):
        for k in range(par_mois):
            jour = min(m + timedelta(days=k), fin)
            armee = k % 2 == 0
            ecrit = not armee or texte_armee or m < date(2025, 1, 1)
            lignes.append((jour, "Armée" if armee else "Mairie", "Rigueur" if ecrit and k % 4 < 2 else None, "Agent", "44"))
    return lignes


def _niveaux(controles: list[dict]) -> dict:
    return {c["code"]: c["niveau"] for c in controles}


def test_controles_ok_puis_degrades():
    offres = _offres(_regulier())
    ctrl, mensuel = suivi.controles_offres(offres, date(2025, 7, 1), {"offres": offres.height})
    n = _niveaux(ctrl)
    assert set(n.values()) == {"ok"}, ctrl
    assert mensuel["n"].sum() == offres.height

    assert _niveaux(suivi.controles_offres(offres, date(2025, 8, 30), None)[0])["fraicheur"] == "alerte"
    assert _niveaux(suivi.controles_offres(offres, date(2025, 10, 1), None)[0])["fraicheur"] == "erreur"
    assert _niveaux(suivi.controles_offres(offres, date(2025, 7, 1), {"offres": 2 * offres.height})[0])["volume"] == "erreur"
    doublon = pl.concat([offres, offres.head(1)])
    assert _niveaux(suivi.controles_offres(doublon, date(2025, 7, 1), None)[0])["doublons"] == "erreur"

    # Le département disparaît des trois derniers mois complets (avril à juin 2025)
    trous = offres.with_columns(departement=pl.when(pl.col("date_publication") >= date(2025, 4, 1)).then(None)
                                .otherwise(pl.col("departement")))
    assert _niveaux(suivi.controles_offres(trous, date(2025, 7, 1), None)[0])["manquants_departement"] == "alerte"


def test_auteur_de_textes_qui_se_tait():
    # L'armée publie toujours autant d'offres mais n'écrit plus de textes depuis janvier 2025 ; fin des données fin 2025
    offres = _offres(_regulier(fin=date(2025, 12, 26), texte_armee=False))
    ctrl = {c["code"]: c for c in suivi.controles_offres(offres, date(2026, 1, 2), None)[0]}
    assert ctrl["contributeurs"]["niveau"] == "alerte" and "Armée" in ctrl["contributeurs"]["detail"]
    assert "Mairie" not in ctrl["contributeurs"]["detail"]


def test_benjamini_hochberg():
    # Exemple calculé à la main : p triés 0,01 0,02 0,03 0,5 -> q = 0,04 0,04 0,04 0,5
    assert suivi._benjamini_hochberg([0.03, 0.5, 0.01, 0.02]) == pytest.approx([0.04, 0.5, 0.04, 0.04])


def _jeu_derive(vraie_hausse: bool):
    """Dix employeurs avec texte. « Gros » cite toujours la compétence X et cesse d'écrire des textes à la période récente :
    en brut, X baisse, Y (citée par les autres) monte mécaniquement. Si `vraie_hausse`, les autres employeurs se mettent
    aussi à citer Z sur la période récente."""
    fin = date(2026, 6, 30)
    lignes, items = [], []
    i = 0
    for org in ["Gros"] + [f"E{k}" for k in range(9)]:
        for jour in range(0, 900, 3 if org == "Gros" else 15):
            d = fin - timedelta(days=jour)
            recent = jour < suivi.RECENT_JOURS
            if org == "Gros" and recent:
                continue
            lignes.append((d, org, "texte", "Agent", "44"))
            formes = ["x"] if org == "Gros" else ["y"] + (["w"] if i % 2 else [])
            if vraie_hausse and org != "Gros" and recent and i % 3:
                formes.append("z")
            if vraie_hausse and org != "Gros" and not recent and i % 10 == 0:
                formes.append("z")
            items += [(i, f) for f in formes]
            i += 1
    offres = _offres(lignes)
    items = pl.DataFrame(items, schema=["annonce_id", "forme"], orient="row").with_columns(pl.col("annonce_id").cast(pl.UInt64))
    formes = pl.DataFrame({"forme": ["x", "y", "w", "z"], "code_ogr": ["1", "2", "3", "4"]})
    return offres, items, formes


def test_derive_a_employeurs_constants(monkeypatch):
    monkeypatch.setattr(suivi, "MIN_EMPLOYEURS", 3)
    offres, items, formes = _jeu_derive(vraie_hausse=False)
    d = suivi.derive(offres, items, formes, {"2": "Y"})
    assert d["employeurs_constants"]["nombre"] == 9  # « Gros » n'a plus d'annonce récente
    assert d["hausses_brutes"][0]["code_ogr"] == "2"  # Y monte en brut, par simple effet de composition
    assert d["significatives"] == []

    offres, items, formes = _jeu_derive(vraie_hausse=True)
    d = suivi.derive(offres, items, formes, {"4": "Z"})
    assert [s["libelle"] for s in d["significatives"]] == ["Z"]
    assert d["employeurs_principaux"][0] == {"organisme": "Gros", "part_recente": 0.0, "part_avant": pytest.approx(243 / (243 + 9 * 49), abs=0.01)}  # tous les 3 jours contre 15


def test_nouveautes_et_historique():
    offres = _offres([(date(2022, 12, 5), "M", "t", "A", "44"), (date(2023, 1, 5), "M", "t", "A", "44"),
                      (date(2023, 2, 5), "M", "t", "A", "44"), (date(2023, 3, 28), "M", "t", "A", "44")])
    items = pl.DataFrame({"annonce_id": [0, 1, 1, 2, 2], "forme": ["a", "a", "b", "b", "c"]}).with_columns(pl.col("annonce_id").cast(pl.UInt64))
    # mars 2023 est le mois en cours (fin au 28) : compté comme complet ; décembre 2022 sert d'historique
    assert suivi.nouveautes_par_mois(offres, items) == [["2023-01", 2, 1], ["2023-02", 2, 1]]

    r = {"date": "2026-10-20", "statut": "alerte", "offres": 3, "derniere_publication": "2026-09-27",
         "controles": [{"code": "fraicheur", "niveau": "ok"}, {"code": "textes", "niveau": "alerte"}]}
    h = suivi.historique([{"date": "2026-10-19"}, {"date": "2026-10-20", "statut": "ok"}], r)
    assert [x["date"] for x in h] == ["2026-10-19", "2026-10-20"] and h[-1]["alertes"] == ["textes"]
    assert suivi.statut(r["controles"]) == "alerte"
