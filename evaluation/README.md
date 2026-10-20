# Évaluation du rattachement des compétences au ROME

Jeux annotés utilisés par le notebook `02_competences.ipynb` pour comparer les méthodes de `offres.competences`.

## Items de compétences

- **Échantillon** : 400 occurrences d'items tirées au hasard (graine 2026) parmi les 657 000 items (avant dédoublonnage
  par annonce) découpés dans les textes « compétences attendues » des offres du service public, soit 321 formes distinctes. `poids` = nombre de tirages
  de la forme : les métriques pondérées reflètent la distribution réelle des items (« rigueur » compte plus qu'un item rare).
- **Pool** : pour chaque item, la meilleure proposition de chaque méthode (dictionnaire, TF-IDF, e5 asymétrique et
  symétrique, MiniLM, deux hybrides), dédoublonnée et mélangée : l'annotateur ne sait pas quelle méthode propose quoi.
- **Verdicts** : `correct` (même compétence, un recruteur taguerait l'offre avec ce libellé), `partiel` (même domaine mais
  nettement plus large ou plus étroit, ou une partie seulement d'un item composé), `faux`. `est_competence` = faux pour les
  fragments, titres de rubrique et informations sur le contrat.
- **Annotateurs** : deux instances de Claude (modèle de langue d'Anthropic) travaillant séparément, consignes identiques,
  41 items annotés par les deux pour mesurer l'accord (kappa de Cohen 0,88). Quand les deux ont annoté, le verdict le plus
  sévère est retenu. Ce n'est pas une annotation humaine : les verdicts peuvent être relus et corrigés dans
  `annotations_brutes.json`, et le notebook se recalcule à partir de ces fichiers.
- **Propositions ajoutées ensuite** : après une correction du nettoyage des items (lot D) et pour les choix des LLM
  (lots E et F), les propositions encore jamais jugées ont été annotées à l'aveugle par d'autres instances, mêlées à
  deux propositions déjà jugées par item pour contrôler l'accord (kappa 0,89 pour le lot D, 0,75 pour le lot E, 0,88
  pour le lot F).
- **Reclassement par LLM** : un LLM choisit, pour chaque item, la meilleure des 10 propositions de l'hybride (ou aucune).
  Fait par Claude sur les candidats de l'hybride e5, ceux de la production (`reclassement_candidats.json`,
  `reclassement_claude.json`), et plus tôt sur ceux de l'hybride MiniLM (`*_minilm.json`) ; par Qwen 2.5 7B et
  Llama 3.1 8B en local via Ollama (`offres reclasser`, sur les candidats MiniLM). Biais possible : le reclasseur Claude
  et les annotateurs sont des modèles de la même famille.

Fichiers :

| Fichier | Contenu |
|---|---|
| `competences_items.csv` | les 321 formes : item, forme, poids, est_competence, annotateurs |
| `competences_propositions.csv` | une ligne par (item, méthode) : proposition ROME, score, verdict |
| `metiers_propositions.csv` | une ligne par (métier, méthode) : appellation et fiche ROME proposées, verdict |
| `annotations_brutes.json` | verdicts de chaque annotateur (lots A à F, et métiers) |
| `reclassement_candidats*.json` | les 10 propositions de l'hybride par item, entrée du reclassement par LLM |
| `reclassement_<modèle>*.json` | les choix de chaque LLM : `{"id", "code"}`, code null si aucun candidat ne convient |

## Métiers

100 métiers de la fonction publique (les 60 plus fréquents, 62 % des offres, et 40 tirés au hasard parmi les autres),
rapprochés des 13 855 appellations du ROME par cinq méthodes. Le verdict porte sur la **fiche ROME** obtenue : `correct` si
ses compétences s'appliquent pour l'essentiel au métier, `partiel` pour une fiche voisine, `faux` sinon. Une seule
annotatrice (instance de Claude).

Les scripts qui ont produit ces fichiers sont dans `scripts/evaluation/` : `reeval.py` recalcule les propositions avec
le code actuel, `ecrire_csv.py` fusionne les verdicts et écrit les CSV. Ils demandent les modèles d'embeddings et
plusieurs minutes de calcul ; le notebook, lui, ne lit que les CSV.
