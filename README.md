# Quelles compétences demande le marché ?

Projet de data science de bout en bout sur les offres d'emploi diffusées par **France Travail** : collecte automatisée via l'API Offres d'emploi v2, extraction des compétences par NLP (dictionnaire, embeddings, LLM en option, comparés sur un échantillon annoté), analyse des salaires et dashboard publié sur GitHub Pages.

## Étapes

1. Cadrage : questions et indicateurs
2. **Collecte et pipeline** (en cours) : photo hebdomadaire de toutes les offres en ligne + nouvelles offres chaque jour
3. Exploration
4. Extraction des compétences (NLP)
5. Structure du marché et zoom métiers de la data
6. Ce qui paie : modèle du salaire
7. Dashboard et article
8. Industrialisation et suivi

## Collecte

L'API ne renvoie jamais plus de 1 150 offres par requête. `offres collecte` coupe donc la période de création en deux tant qu'une tranche dépasse ce plafond (puis par type de contrat pour les rafales d'offres créées à la même seconde), et pagine chaque tranche par 150.

```bash
pip install -e ".[dev]"
export FRANCE_TRAVAIL_CLIENT_ID=... FRANCE_TRAVAIL_CLIENT_SECRET=...
offres --dossier donnees collecte --mode jour    # offres créées ces 3 derniers jours
offres --dossier donnees collecte --mode stock   # toutes les offres en ligne
```

Le workflow « Collecte des offres » tourne chaque matin et publie les fichiers Parquet dans la release [`donnees`](../../releases/tag/donnees) :

| Fichier | Contenu |
|---|---|
| `offres_AAAA-MM-JJ_jour.parquet` / `_stock.parquet` | une ligne par offre, colonnes à plat ; listes (compétences, formations, langues...) en JSON |
| `index.parquet` | toutes les offres déjà vues : première et dernière apparition, en ligne ou non (durée de vie) |
| `collecte_*.json` | rapport de chaque passage : nombre d'offres, tranches, appels, offres perdues au plafond |
| `ref_*.json` | référentiels de l'API (métiers ROME, appellations, départements...) |

Identifiants : secrets GitHub Actions `FRANCE_TRAVAIL_CLIENT_ID` et `FRANCE_TRAVAIL_CLIENT_SECRET` (application francetravail.io abonnée à l'API Offres d'emploi v2).

Licence MIT.
