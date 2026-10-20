"""Reclassement par LLM local (Ollama) : pour chaque item, le modèle choisit la meilleure des propositions ROME de la
méthode hybride, ou aucune.

Tourne sur une machine avec Ollama (`ollama serve`, modèle déjà téléchargé avec `ollama pull`), pas dans GitHub Actions :

    offres reclasser --modele qwen2.5:7b --entree evaluation/reclassement_candidats.json --sortie choix.json

L'entrée est une liste JSON de {"id", "item", "candidats": [{"code", "libelle"}, ...]} ; la sortie, une liste de
{"id", "code"} (code null si aucun candidat ne convient). Les items déjà présents dans la sortie sont sautés : on peut
interrompre et relancer ; un item dont la requête échoue n'est pas enregistré et sera retenté.

Le notebook 02 compare ce reclassement local au même exercice fait par Claude sur l'échantillon annoté.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

URL_OLLAMA = "http://localhost:11434/api/chat"
ERREURS = (requests.RequestException, ValueError, KeyError, TypeError)

CONSIGNE = """Tu rattaches des compétences tirées d'offres d'emploi de la fonction publique française au référentiel ROME.
Pour chaque item, choisis le numéro du candidat qui désigne le mieux la même compétence (même sens, pas seulement les mêmes
mots ; pour un item composé comme « autonomie et rigueur », celui qui en couvre le plus). Réponds 0 si aucun candidat
n'est au moins dans le même domaine, ou si l'item n'est pas une compétence (fragment de phrase, titre de rubrique,
information sur le contrat).
Exemples : « RIGUEUR » parmi [1. CQP accrocheur-rigger, 2. Faire preuve de rigueur et de précision] -> 2 ;
« Réactivité » parmi [1. Gestion des réactifs chimiques, 2. Analyse chimique] -> 0."""


def _schema(n: int) -> dict:
    return {
        "type": "object",
        "properties": {"choix": {"type": "array", "minItems": n, "maxItems": n,
                                 "items": {"type": "object", "properties": {"item": {"type": "integer"},
                                                                            "candidat": {"type": "integer"}},
                                           "required": ["item", "candidat"]}}},
        "required": ["choix"],
    }


def _prompt(lot: list[dict]) -> str:
    blocs = []
    for n, entree in enumerate(lot, start=1):
        cands = "\n".join(f"  {k}. {c['libelle']}" for k, c in enumerate(entree["candidats"], start=1))
        blocs.append(f"Item {n} : « {entree['item']} »\n{cands}")
    return "\n\n".join(blocs) + f"\n\nRéponds en JSON : un choix par item, de l'item 1 à l'item {len(lot)}."


def choisir(lot: list[dict], modele: str, url: str = URL_OLLAMA) -> list[str | None]:
    r = requests.post(url, timeout=600, json={
        "model": modele, "stream": False, "format": _schema(len(lot)),
        "options": {"temperature": 0, "num_ctx": 8192},
        "messages": [{"role": "system", "content": CONSIGNE}, {"role": "user", "content": _prompt(lot)}],
    })
    r.raise_for_status()
    reponse = json.loads(r.json()["message"]["content"])["choix"]
    if len(reponse) != len(lot):
        raise ValueError(f"{len(reponse)} choix pour {len(lot)} items")
    # Lu par position : le schéma fixe la longueur de la liste, les numéros d'items écrits par le modèle sont ignorés
    codes: list[str | None] = []
    for c, entree in zip(reponse, lot):
        k = int(c["candidat"])
        codes.append(entree["candidats"][k - 1]["code"] if 1 <= k <= len(entree["candidats"]) else None)
    return codes


def reclasser(entree: Path, sortie: Path, modele: str, taille_lot: int = 8, url: str = URL_OLLAMA) -> None:
    items = json.loads(entree.read_text(encoding="utf-8"))
    faits = {d["id"]: d for d in json.loads(sortie.read_text(encoding="utf-8"))} if sortie.exists() else {}
    a_faire = [i for i in items if i["id"] not in faits]
    print(f"{len(items)} items, {len(a_faire)} à faire avec {modele}")
    depart = time.monotonic()
    echecs = 0
    for debut in range(0, len(a_faire), taille_lot):
        lot = a_faire[debut : debut + taille_lot]
        try:
            resultats = list(zip(lot, choisir(lot, modele, url)))
        except ERREURS as e:
            print(f"  lot {debut} : {e} ; nouvel essai item par item")
            resultats = []
            for entree_seule in lot:
                try:
                    resultats.append((entree_seule, choisir([entree_seule], modele, url)[0]))
                except ERREURS as e_seul:
                    # Pas enregistré (un échec n'est pas une abstention) : l'item sera retenté au prochain lancement
                    echecs += 1
                    print(f"    item {entree_seule['id']} : {e_seul}")
        for e_, code in resultats:
            faits[e_["id"]] = {"id": e_["id"], "code": code}
        if (debut // taille_lot) % 20 == 0 or debut + taille_lot >= len(a_faire):
            sortie.write_text(json.dumps(list(faits.values()), ensure_ascii=False), encoding="utf-8")
            ecoule = time.monotonic() - depart
            fait = min(debut + taille_lot, len(a_faire))
            print(f"  {fait}/{len(a_faire)} items, {ecoule:.0f} s, ~{ecoule / fait * (len(a_faire) - fait) / 60:.0f} min restantes")
    if echecs:
        print(f"{echecs} items en échec, non enregistrés : relancer la même commande pour les retenter")
