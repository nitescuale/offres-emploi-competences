"""Client de l'API Offres d'emploi v2 de France Travail (OAuth2, client credentials).

Les identifiants viennent des variables d'environnement `FRANCE_TRAVAIL_CLIENT_ID` et `FRANCE_TRAVAIL_CLIENT_SECRET`
(secrets GitHub Actions) ; ils ne sont jamais écrits sur disque ni affichés.
"""

from __future__ import annotations

import os
import re
import time
from datetime import UTC, datetime, timedelta

import requests

URL_JETON = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
URL_API = "https://api.francetravail.io/partenaire/offresdemploi/v2"
PORTEE = "api_offresdemploiv2 o2dsoffre"

TAILLE_PAGE = 150  # maximum de l'API par appel
PLAFOND = 1150  # au-delà, l'API refuse de paginer (range max 1000-1149)
INTERVALLE_MIN = 0.12  # l'API accepte une dizaine d'appels par seconde


class ErreurApi(RuntimeError):
    pass


def format_date(moment: datetime) -> str:
    """Format attendu par minCreationDate / maxCreationDate."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def total_content_range(entete: str | None) -> int | None:
    """`offres 0-149/2345` -> 2345."""
    if not entete:
        return None
    m = re.search(r"/(\d+)\s*$", entete)
    return int(m.group(1)) if m else None


class Client:
    def __init__(self, client_id: str | None = None, client_secret: str | None = None, portee: str | None = None):
        self.client_id = client_id or os.environ.get("FRANCE_TRAVAIL_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("FRANCE_TRAVAIL_CLIENT_SECRET")
        if not self.client_id or not self.client_secret:
            raise ErreurApi("Identifiants manquants : définir FRANCE_TRAVAIL_CLIENT_ID et FRANCE_TRAVAIL_CLIENT_SECRET")
        self.portee = portee or os.environ.get("FRANCE_TRAVAIL_PORTEE") or PORTEE
        self.session = requests.Session()
        self._jeton: str | None = None
        self._expire = datetime.min.replace(tzinfo=UTC)
        self._dernier_appel = 0.0
        self.appels = 0

    def jeton(self) -> str:
        if self._jeton and datetime.now(UTC) < self._expire:
            return self._jeton
        r = self.session.post(
            URL_JETON,
            params={"realm": "/partenaire"},
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": self.portee,
            },
            timeout=60,
        )
        if r.status_code != 200:
            # Le corps d'erreur OAuth ne contient pas le secret
            raise ErreurApi(f"Jeton refusé ({r.status_code}) : {r.text[:300]}")
        corps = r.json()
        self._jeton = corps["access_token"]
        self._expire = datetime.now(UTC) + timedelta(seconds=int(corps.get("expires_in", 1499)) - 60)
        return self._jeton

    def get(self, chemin: str, params: dict | None = None, essais: int = 6) -> requests.Response:
        for essai in range(essais):
            attente = INTERVALLE_MIN - (time.monotonic() - self._dernier_appel)
            if attente > 0:
                time.sleep(attente)
            self._dernier_appel = time.monotonic()
            self.appels += 1
            try:
                r = self.session.get(
                    f"{URL_API}{chemin}",
                    params=params,
                    headers={"Authorization": f"Bearer {self.jeton()}", "Accept": "application/json"},
                    timeout=60,
                )
            except requests.RequestException as e:
                if essai == essais - 1:
                    raise
                print(f"  réseau : {e}, nouvel essai")
                time.sleep(2**essai)
                continue
            if r.status_code == 401:
                self._jeton = None
                continue
            if r.status_code in (429, 500, 502, 503, 504):
                pause = float(r.headers.get("Retry-After") or 2**essai)
                time.sleep(min(pause, 60))
                continue
            return r
        raise ErreurApi(f"{chemin} : échec après {essais} essais (dernier code {r.status_code})")

    def chercher(self, criteres: dict, debut: int = 0, fin: int = TAILLE_PAGE - 1) -> tuple[list[dict], int]:
        """Une page de résultats et le nombre total d'offres correspondant aux critères."""
        r = self.get("/offres/search", {**criteres, "range": f"{debut}-{fin}"})
        if r.status_code == 204:
            return [], 0
        if r.status_code not in (200, 206):
            raise ErreurApi(f"Recherche {criteres} [{debut}-{fin}] : {r.status_code} {r.text[:300]}")
        resultats = r.json().get("resultats", [])
        total = total_content_range(r.headers.get("Content-Range"))
        return resultats, total if total is not None else len(resultats)

    def compter(self, criteres: dict) -> int:
        return self.chercher(criteres, 0, 0)[1]

    def referentiel(self, nom: str) -> list[dict]:
        r = self.get(f"/referentiel/{nom}")
        if r.status_code != 200:
            raise ErreurApi(f"Référentiel {nom} : {r.status_code} {r.text[:300]}")
        return r.json()
