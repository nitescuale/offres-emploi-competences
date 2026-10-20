import random
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
    ctrl, mensuel = suivi.controles_offres(offres, date(2025, 7, 1), offres.height)
    n = _niveaux(ctrl)
    assert set(n.values()) == {"ok"}, ctrl
    assert mensuel["n"].sum() == offres.height
    # Une offre le 26 juin : juin compte comme complet, mais il est ramené au mois entier avant comparaison à juin 2024
    juin = _offres(_regulier() + [(date(2025, 6, 26), "Mairie", None, "Agent", "44")])
    mois = {c["code"]: c for c in suivi.controles_offres(juin, date(2025, 7, 1), None)[0]}["volume_mensuel"]
    assert "06/2025 (données jusqu'au 26" in mois["detail"] and mois["valeur"] == pytest.approx(21 * 30 / 26 / 20, abs=1e-3)

    assert _niveaux(suivi.controles_offres(offres, date(2025, 8, 30), None)[0])["fraicheur"] == "alerte"
    assert _niveaux(suivi.controles_offres(offres, date(2025, 10, 1), None)[0])["fraicheur"] == "erreur"
    assert _niveaux(suivi.controles_offres(offres, date(2025, 7, 1), 2 * offres.height)[0])["volume"] == "erreur"
    doublon = pl.concat([offres, offres.head(1)])
    assert _niveaux(suivi.controles_offres(doublon, date(2025, 7, 1), None)[0])["doublons"] == "erreur"

    # Le département disparaît des trois derniers mois complets (avril à juin 2025)
    trous = offres.with_columns(departement=pl.when(pl.col("date_publication") >= date(2025, 4, 1)).then(None)
                                .otherwise(pl.col("departement")))
    assert _niveaux(suivi.controles_offres(trous, date(2025, 7, 1), None)[0])["manquants_departement"] == "alerte"


def test_date_aberrante_ne_masque_pas_un_fichier_perime():
    offres = _offres(_regulier() + [(date(2027, 3, 1), "Mairie", None, "Agent", "44")])
    ctrl = {c["code"]: c for c in suivi.controles_offres(offres, date(2025, 10, 1), None)[0]}
    assert ctrl["fraicheur"]["niveau"] == "erreur" and ctrl["fraicheur"]["valeur"] == 103  # dernière offre plausible le 20 juin
    assert ctrl["dates_futures"]["niveau"] == "alerte"


def test_volume_compare_au_plus_haut_recent():
    # Après une baisse, le contrôle suivant compare toujours au plus haut : l'erreur ne s'efface pas d'elle-même
    assert suivi.volume_reference([{"offres": 100}, {"offres": 80}]) == 100
    assert suivi.volume_reference([]) is None


def test_controles_competences():
    offres = _offres([(date(2025, 1, 1), "M", "texte", "Agent" if k else "Inconnu", "44") for k in range(10)])
    items = pl.DataFrame({"annonce_id": list(range(9)), "forme": ["a"] * 8 + ["b"]}).with_columns(pl.col("annonce_id").cast(pl.UInt64))
    formes = pl.DataFrame({"forme": ["a", "b"], "code_ogr": ["1", None], "version": ["v1", "v1"]})
    metiers = pl.DataFrame({"metier": ["Agent"]})
    n = _niveaux(suivi.controles_competences(offres, items, formes, metiers, {"1"}, "v1"))
    assert n == {"couverture": "alerte", "formes": "erreur", "catalogue": "ok", "version": "ok", "metiers": "alerte"}
    n = _niveaux(suivi.controles_competences(offres, items, formes.fill_null("9"), metiers, {"1"}, "v2"))
    assert (n["formes"], n["catalogue"], n["version"]) == ("ok", "erreur", "alerte")


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
    """32 employeurs avec texte. « Gros » cite toujours la compétence X et cesse d'écrire des textes à la période récente :
    en brut, X baisse, Y (citée par les autres) monte mécaniquement. Si `vraie_hausse`, les autres employeurs se mettent
    aussi à citer Z sur la période récente, et cessent presque de citer V (une vraie baisse, qui ne doit pas être
    annoncée comme compétence émergente)."""
    fin = date(2026, 6, 30)
    hasard = random.Random(0)
    lignes, items = [], []
    i = 0
    for org in ["Gros"] + [f"E{k}" for k in range(31)]:
        for jour in range(0, 900, 3 if org == "Gros" else 15):
            d = fin - timedelta(days=jour)
            recent = jour < suivi.RECENT_JOURS
            if org == "Gros" and recent:
                continue
            lignes.append((d, org, "texte", "Agent", "44"))
            if org == "Gros":
                formes = ["x"]
            else:
                formes = ["y"] + (["w"] if hasard.random() < 0.5 else [])  # W : même fréquence dans les deux périodes
                if vraie_hausse and hasard.random() < (0.67 if recent else 0.1):
                    formes.append("z")
                if vraie_hausse and hasard.random() < (0.05 if recent else 0.5):
                    formes.append("v")
            items += [(i, f) for f in formes]
            i += 1
    offres = _offres(lignes)
    items = pl.DataFrame(items, schema=["annonce_id", "forme"], orient="row").with_columns(pl.col("annonce_id").cast(pl.UInt64))
    formes = pl.DataFrame({"forme": ["x", "y", "w", "z", "v"], "code_ogr": ["1", "2", "3", "4", "5"]})
    return offres, items, formes


def test_derive_a_employeurs_constants(monkeypatch):
    monkeypatch.setattr(suivi, "MIN_EMPLOYEURS", 3)
    offres, items, formes = _jeu_derive(vraie_hausse=False)
    d = suivi.derive(offres, items, formes, {"2": "Y"})
    assert d["employeurs_constants"]["nombre"] == 31  # « Gros » n'a plus d'annonce récente
    assert d["hausses_brutes"][0]["code_ogr"] == "2"  # Y monte en brut, par simple effet de composition
    assert d["significatives"] == []

    offres, items, formes = _jeu_derive(vraie_hausse=True)
    d = suivi.derive(offres, items, formes, {"4": "Z", "5": "V"})
    assert [s["libelle"] for s in d["significatives"]] == ["Z"]  # V baisse nettement, mais n'est pas une hausse
    assert {c["libelle"]: c["q"] for c in d["hausses_constantes"]}["V"] < suivi.SEUIL_FDR
    z = d["significatives"][0]
    assert z["ecart_constant"] - z["ic"] > 0
    # « Gros » publie tous les 3 jours, les autres tous les 15
    assert d["employeurs_principaux"][0] == {"organisme": "Gros", "part_recente": 0.0, "part_avant": pytest.approx(243 / (243 + 31 * 49), abs=0.01)}

    # Sous 30 employeurs présents dans les deux périodes, aucun test
    peu = offres.filter(pl.col("organisme").is_in(["Gros", "E0", "E1", "E2"]))
    d = suivi.derive(peu, items, formes, {})
    assert d["competences_testees"] == 0 and d["significatives"] == []


def test_nouveautes_et_historique():
    offres = _offres([(date(2022, 12, 5), "M", "t", "A", "44"), (date(2023, 1, 5), "M", "t", "A", "44"),
                      (date(2023, 2, 5), "M", "t", "A", "44"), (date(2023, 3, 28), "M", "t", "A", "44")])
    items = pl.DataFrame({"annonce_id": [0, 1, 1, 2, 2], "forme": ["a", "a", "b", "b", "c"]}).with_columns(pl.col("annonce_id").cast(pl.UInt64))
    # décembre 2022 sert d'historique ; mars 2023 (fin au 28, donc complet) n'a pas d'item et n'apparaît pas
    assert suivi.nouveautes_par_mois(offres, items) == [["2023-01", 2, 1], ["2023-02", 2, 1]]

    r = {"date": "2026-10-20", "statut": "alerte", "offres": 3, "derniere_publication": "2026-09-27",
         "controles": [{"code": "fraicheur", "niveau": "ok"}, {"code": "textes", "niveau": "alerte"}]}
    h = suivi.historique([{"date": "2026-10-19"}, {"date": "2026-10-20", "statut": "ok"}], r)
    assert [x["date"] for x in h] == ["2026-10-19", "2026-10-20"] and h[-1]["alertes"] == ["textes"]
    assert suivi.statut(r["controles"]) == "alerte"


def test_copier_suivi_sans_rapport(tmp_path, monkeypatch):
    import requests

    from offres import web

    def absent(nom, rafraichir=False):
        raise requests.ConnectionError("hors ligne")

    monkeypatch.setattr(web.donnees, "chemin", absent)
    web.copier_suivi(tmp_path)  # la construction du site continue
    assert list(tmp_path.iterdir()) == []
