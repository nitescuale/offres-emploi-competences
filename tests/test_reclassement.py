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
