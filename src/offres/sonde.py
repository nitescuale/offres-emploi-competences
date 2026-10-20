"""Sonde des API France Travail : quelles portées OAuth et quelles routes répondent avec les identifiants du dépôt.

Sert au diagnostic (abonnements de l'application) ; n'affiche jamais les identifiants ni le jeton.
"""

from __future__ import annotations

import requests

from offres.api import URL_JETON, Client, ErreurApi

PORTEES = {
    "Offres d'emploi v2": "api_offresdemploiv2 o2dsoffre",
    "ROME 4.0 Compétences": "api_rome-competencesv1 nomenclatureRome",
    "ROME 4.0 Compétences (variante)": "api_rome-competencesv1",
}
ROUTES_ROME = [
    "/rome-competences/v1/competences/competence",
    "/rome-competences/v1/competences/macro-competence",
    "/rome-competences/v1/competences/savoir",
    "/rome-competences/v1/competences/arborescence",
    "/rome-competences/v1/competences/domaine-competence",
]


def sonder() -> None:
    for nom, portee in PORTEES.items():
        try:
            client = Client(portee=portee)
            client.jeton()
        except ErreurApi as e:
            print(f"✗ {nom} ({portee}) : {e}")
            continue
        print(f"✓ {nom} ({portee}) : jeton accordé")
        if "rome" not in portee:
            continue
        for route in ROUTES_ROME:
            r = requests.get(
                f"https://api.francetravail.io/partenaire{route}",
                headers={"Authorization": f"Bearer {client.jeton()}", "Accept": "application/json"},
                timeout=60,
            )
            print(f"   {route} -> {r.status_code} {len(r.content)} o : {r.text[:400]!r}")


if __name__ == "__main__":
    print(URL_JETON)
    sonder()
