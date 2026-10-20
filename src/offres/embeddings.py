"""Modèles de phrases multilingues, chargés depuis la release `modeles` du dépôt (copie de Hugging Face faite par le
workflow « Modèles d'embeddings », pour fonctionner là où Hugging Face n'est pas joignable).

- `multilingual-e5-small` (MIT) : entraîné pour la recherche, attend les préfixes « query: » et « passage: » ;
- `paraphrase-multilingual-MiniLM-L12-v2` (Apache 2.0) : entraîné sur des paraphrases, sans préfixe.
"""

from __future__ import annotations

import tarfile

import numpy as np
import requests

from offres.donnees import CACHE

URL_RELEASE = "https://github.com/nitescuale/offres-emploi-competences/releases/download/modeles"
MODELES = {
    "e5": ("multilingual-e5-small", ("query: ", "passage: ")),
    "minilm": ("paraphrase-multilingual-MiniLM-L12-v2", ("", "")),
}


def dossier_modele(nom: str) -> str:
    """Dossier local du modèle, téléchargé et décompressé au besoin."""
    depot, _ = MODELES[nom]
    dossier = CACHE / "modeles" / depot
    if not (dossier / "config.json").exists():
        dossier.parent.mkdir(parents=True, exist_ok=True)
        archive = dossier.parent / f"{depot}.tar.gz"
        with requests.get(f"{URL_RELEASE}/{depot}.tar.gz", stream=True, timeout=600) as r:
            r.raise_for_status()
            with archive.open("wb") as f:
                for morceau in r.iter_content(1 << 20):
                    f.write(morceau)
        with tarfile.open(archive) as tar:
            tar.extractall(dossier.parent, filter="data")
        archive.unlink()
    return str(dossier)


class Modele:
    """Encode des textes en vecteurs normalisés : le produit scalaire est alors la similarité cosinus."""

    def __init__(self, nom: str = "e5", appareil: str = "cpu"):
        from sentence_transformers import SentenceTransformer

        self.nom = nom
        self.prefixes = MODELES[nom][1]
        self.st = SentenceTransformer(dossier_modele(nom), device=appareil)

    def encoder(self, textes: list[str], requete: bool = True, lot: int = 256) -> np.ndarray:
        prefixe = self.prefixes[0] if requete else self.prefixes[1]
        return self.st.encode([prefixe + t for t in textes], batch_size=lot, normalize_embeddings=True,
                              convert_to_numpy=True, show_progress_bar=False)
