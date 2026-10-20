# Quelles compétences demande le marché ?

[![Tests](https://github.com/nitescuale/offres-emploi-competences/actions/workflows/ci.yml/badge.svg)](https://github.com/nitescuale/offres-emploi-competences/actions/workflows/ci.yml)

Projet de data science de bout en bout sur les offres d'emploi publiques : les **offres des trois fonctions publiques** (Choisir le service public, open data, 1,6 million d'offres depuis 2022) et, dès que l'accès à l'API sera accordé, celles diffusées par **France Travail** (API Offres d'emploi v2, désormais en accès restreint) ; extraction des compétences par NLP (dictionnaire, embeddings et LLM comparés sur un échantillon annoté ; la version publiée se passe de LLM), analyse des salaires et dashboard publié sur GitHub Pages.

## Étapes

1. Cadrage : questions et indicateurs
2. Collecte et pipeline (fait) : offres du service public chaque semaine ; France Travail prêt, en attente de l'accès
3. Exploration (fait) : [`notebooks/01_exploration.ipynb`](notebooks/01_exploration.ipynb)
4. Extraction des compétences (fait) : [`notebooks/02_competences.ipynb`](notebooks/02_competences.ipynb), évaluation dans [`evaluation/`](evaluation/)
5. Structure du marché et zoom métiers de la data (fait) : [`notebooks/03_structure.ipynb`](notebooks/03_structure.ipynb)
6. Postes qui peinent à recruter (fait) : [`notebooks/04_recrutement.ipynb`](notebooks/04_recrutement.ipynb) ; pas de salaire dans les offres du service public, la cible est la republication du poste (le modèle du salaire reviendra avec les offres France Travail)
7. Site, tableau de bord et article (fait) : [`site/`](site/), publié sur GitHub Pages par le workflow « Site »
8. Industrialisation et suivi (fait) : workflow « Suivi » quotidien ([`src/offres/suivi.py`](src/offres/suivi.py)), page « Coulisses » du site

## Site

`offres site --sortie _site` assemble un site statique (sans serveur) dans `_site/` :

- `index.html` : l'article de synthèse, avec les figures des notebooks ;
- `tableau.html` : le tableau de bord par métier (884), territoire (région, département) et année : offres par mois, télétravail, catégories, management, taux de republication, carte des départements, compétences citées et fiche ROME ;
- `suivi.html` : les « Coulisses », avec la chaîne des workflows (état lu en direct sur l'API GitHub), les contrôles du jour et leur historique, et la dérive des compétences ;
- `outil.html` : « Mes compétences », qui découpe une offre ou un CV et rattache chaque item au ROME dans le navigateur. La découpe et TF-IDF sont réécrits en JavaScript ([`site/js/extraction.js`](site/js/extraction.js)) et vérifiés identiques au Python par `tests/test_site.py` ; les formes déjà vues dans les offres reprennent le rattachement de la méthode publiée.

Les données du site (`donnees/`, `outil/`) sont calculées par [`src/offres/web.py`](src/offres/web.py) à partir de la release `donnees`. Le workflow « Site » reconstruit et publie le tout après chaque passage du suivi, donc chaque jour ; la publication demande GitHub Pages réglé sur la source « GitHub Actions ».

## Suivi de production

`offres suivi --sortie suivi --historique suivi_historique.json` contrôle les fichiers de la release et écrit `suivi_dernier.json` et `suivi_historique.json`, publiés dans la release par le workflow « Suivi » (chaque jour à 5 h 30 UTC et après chaque mise à jour des compétences). Chaîne : offres (lundi) → compétences → suivi → site.

- **Contrôles** : fraîcheur de la dernière offre, volume total et mensuel, doublons, dates futures, départements inconnus, valeurs manquantes, part d'offres avec un texte de compétences, gros auteurs de textes qui cessent d'en écrire, couverture et version des rattachements au ROME. Un contrôle en erreur fait échouer le workflow (courriel de GitHub) ; le rapport est publié quand même et affiché sur le site.
- **Dérive** : compétences ROME citées ces six derniers mois contre les deux années précédentes, en brut puis à employeurs constants (écart par employeur présent dans les deux périodes, test t, correction de Benjamini-Hochberg), et part mensuelle de formes jamais vues.
- **Premier constat** (octobre 2026) : depuis novembre 2025, les services des armées, auteurs d'environ 38 % des textes de compétences en 2023-2025, n'en écrivent presque plus. Les hausses brutes de compétences (travail en équipe, bureautique…) viennent de ce changement d'auteurs : à employeurs constants, aucune des 887 compétences testées ne progresse nettement.

## Données

### Offres du service public (source principale)

`offres --dossier donnees csp` télécharge chaque fichier annuel du jeu [« Les offres diffusées sur Choisir le service public »](https://www.data.gouv.fr/datasets/les-offres-diffusees-sur-choisir-le-service-public) (DGAFP, Licence Ouverte), renomme et type les colonnes, extrait le département, la catégorie (A+, A, B, C) et le niveau d'études, puis consolide les années en gardant pour chaque référence la version la plus récente. Le workflow « Offres Choisir le service public » tourne chaque lundi.

| Fichier (release `donnees`) | Contenu |
|---|---|
| `csp_offres.parquet` | une ligne par offre : métier, intitulé, versant, catégorie, employeur, département, télétravail, niveau d'études, dates, texte « compétences attendues » (≈ 5 % des offres) |
| `csp_rapport.json` | nombre d'offres, période couverte, offres par année |
| `rome_*` | référentiel ROME 4.0 (compétences, savoirs, métiers), workflow « Référentiel ROME » |

Dictionnaire des colonnes et pièges connus : [docs/dictionnaire-donnees.md](docs/dictionnaire-donnees.md).

### Offres France Travail (quand l'accès sera accordé)

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

## Licences

Code sous licence MIT. Données dérivées publiées sous Licence Ouverte 2.0, avec mention des sources : « Les offres diffusées sur Choisir le service public » (DGAFP) et le Répertoire opérationnel des métiers et des emplois ROME 4.0 (France Travail), via data.gouv.fr. Les conditions d'utilisation de l'API France Travail seront vérifiées avant de republier ses offres brutes.
