from datetime import UTC, datetime, timedelta

import polars as pl

from offres import collecte
from offres.api import PLAFOND, total_content_range


class FauxClient:
    """Imite l'API : filtre par date de création (bornes inclusives, à la seconde) et refuse d'aller au-delà du plafond."""

    def __init__(self, offres):
        self.offres = offres
        self.appels = 0

    def chercher(self, criteres, debut=0, fin=149):
        self.appels += 1
        assert fin < PLAFOND and fin - debut < 150
        mini = datetime.strptime(criteres["minCreationDate"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        maxi = datetime.strptime(criteres["maxCreationDate"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        choix = [
            o for o in self.offres
            if mini <= o["_date"] <= maxi and ("typeContrat" not in criteres or o["typeContrat"] == criteres["typeContrat"])
        ]
        choix.sort(key=lambda o: o["_date"], reverse=True)
        return choix[debut:fin + 1], len(choix)


def fabriquer(n, depart, pas):
    return [
        {"id": f"O{i}", "_date": depart + i * pas, "dateCreation": (depart + i * pas).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
         "typeContrat": ["CDI", "CDD", "MIS"][i % 3], "intitule": f"Offre {i}"}
        for i in range(n)
    ]


def test_bissection_recupere_toutes_les_offres():
    depart = datetime(2026, 1, 1, tzinfo=UTC)
    offres = fabriquer(5000, depart, timedelta(minutes=7))
    journal = []
    vues = list(collecte.offres_periode(FauxClient(offres), depart - timedelta(days=30), depart + timedelta(days=60), journal=journal))
    assert {o["id"] for o in vues} == {o["id"] for o in offres}
    assert all(t["total"] <= PLAFOND for t in journal)
    assert not any(t["tronque"] for t in journal)


def test_rafale_a_la_meme_seconde_decoupee_par_contrat():
    depart = datetime(2026, 1, 1, tzinfo=UTC)
    rafale = [{**o, "id": f"R{i}"} for i, o in enumerate(fabriquer(3000, depart, timedelta(0)))]
    vues = list(collecte.offres_periode(FauxClient(rafale), depart - timedelta(days=1), depart + timedelta(days=1)))
    assert len({o["id"] for o in vues}) == 3000


def test_tranche_impossible_a_couper_est_tronquee_et_signalee():
    depart = datetime(2026, 1, 1, tzinfo=UTC)
    rafale = [{**o, "id": f"R{i}", "typeContrat": "CDI"} for i, o in enumerate(fabriquer(2000, depart, timedelta(0)))]
    journal = []
    vues = list(collecte.offres_periode(FauxClient(rafale), depart - timedelta(days=1), depart + timedelta(days=1), journal=journal))
    assert len(vues) == PLAFOND
    assert any(t["tronque"] and t["total"] == 2000 for t in journal)


def test_content_range():
    assert total_content_range("offres 0-149/2345") == 2345
    assert total_content_range(None) is None


def test_table_et_index():
    vue1 = datetime(2026, 10, 1, tzinfo=UTC)
    offres = [
        {"id": "A", "dateCreation": "2026-09-30T10:00:00.000Z", "dateActualisation": "2026-09-30T10:00:00.000Z",
         "lieuTravail": {"libelle": "75 - Paris", "codePostal": 75001, "latitude": 48.8}, "origineOffre": {"origine": 1},
         "competences": [{"code": "123", "libelle": "Python", "exigence": "E"}], "salaire": {"libelle": "Annuel de 40000 Euros"}},
        {"id": "B", "dateCreation": "2026-09-30T11:00:00.000Z"},
    ]
    table = collecte.en_table(offres, vue1)
    assert table.height == 2
    assert table.filter(pl.col("id") == "A")["code_postal"][0] == "75001"
    assert '"Python"' in table.filter(pl.col("id") == "A")["competences"][0]

    index = collecte.mettre_a_jour_index(None, table, vue1, complet=True)
    assert index["en_ligne"].all()
    vue2 = vue1 + timedelta(days=7)
    table2 = collecte.en_table([offres[0], {"id": "C", "dateCreation": "2026-10-07T09:00:00.000Z"}], vue2)
    index = collecte.mettre_a_jour_index(index, table2, vue2, complet=True)
    lignes = {r["id"]: r for r in index.iter_rows(named=True)}
    assert lignes["A"]["premiere_vue"] == vue1 and lignes["A"]["derniere_vue"] == vue2 and lignes["A"]["en_ligne"]
    assert not lignes["B"]["en_ligne"]
    assert lignes["C"]["en_ligne"]


def test_offres_hors_types_de_contrat_comptees():
    depart = datetime(2026, 1, 1, tzinfo=UTC)
    rafale = [{**o, "id": f"R{i}", "typeContrat": "XYZ" if i < 300 else o["typeContrat"]}
              for i, o in enumerate(fabriquer(1500, depart, timedelta(0)))]
    journal = []
    vues = list(collecte.offres_periode(FauxClient(rafale), depart - timedelta(days=1), depart + timedelta(days=1), journal=journal))
    assert len(vues) == 1200
    assert sum(t["manquantes"] for t in journal) == 300


def test_retry_after():
    from offres.api import attente_retry_after

    assert attente_retry_after("5", 1) == 5
    assert attente_retry_after(None, 3) == 3
    assert attente_retry_after("Wed, 21 Oct 2015 07:28:00 GMT", 2) == 0
    assert attente_retry_after("n'importe quoi", 2) == 2
