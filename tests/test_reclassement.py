import json

from offres import reclassement


class FausseReponse:
    def __init__(self, choix):
        self.choix = choix

    def raise_for_status(self):
        pass

    def json(self):
        return {"message": {"content": json.dumps({"choix": self.choix})}}


def test_choisir_traduit_les_numeros_en_codes(monkeypatch):
    lot = [
        {"id": 0, "item": "RIGUEUR", "candidats": [{"code": "a", "libelle": "CQP accrocheur-rigger"},
                                                    {"code": "b", "libelle": "Faire preuve de rigueur"}]},
        {"id": 1, "item": "etc", "candidats": [{"code": "c", "libelle": "Techniques de soudure"}]},
        {"id": 2, "item": "Excel", "candidats": [{"code": "d", "libelle": "Tableur"}]},
    ]
    envoye = {}

    def faux_post(url, json, timeout):
        envoye.update(json)
        return FausseReponse([{"item": 1, "candidat": 2}, {"item": 2, "candidat": 0}, {"item": 3, "candidat": 9}])

    monkeypatch.setattr(reclassement.requests, "post", faux_post)
    assert reclassement.choisir(lot, "modele") == ["b", None, None]
    assert envoye["options"]["temperature"] == 0
    assert "Item 3 : « Excel »" in envoye["messages"][1]["content"]


def test_reclasser_ne_garde_pas_les_echecs(monkeypatch, tmp_path):
    entree = tmp_path / "entree.json"
    sortie = tmp_path / "sortie.json"
    entree.write_text(json.dumps([
        {"id": i, "item": f"item {i}", "candidats": [{"code": f"c{i}", "libelle": "x"}]} for i in range(3)
    ]), encoding="utf-8")
    panne = {"active": True}

    def faux_choisir(lot, modele, url):
        if panne["active"] and any(e["id"] == 1 for e in lot):
            raise reclassement.requests.ConnectionError("Ollama arrêté")
        return ["c" + str(e["id"]) for e in lot]

    monkeypatch.setattr(reclassement, "choisir", faux_choisir)
    reclassement.reclasser(entree, sortie, "modele")
    assert sorted(d["id"] for d in json.loads(sortie.read_text(encoding="utf-8"))) == [0, 2]
    # Relancé une fois la panne finie, seul l'item en échec est refait
    panne["active"] = False
    reclassement.reclasser(entree, sortie, "modele")
    assert {d["id"]: d["code"] for d in json.loads(sortie.read_text(encoding="utf-8"))} == {0: "c0", 1: "c1", 2: "c2"}
