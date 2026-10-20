# Évaluation du rattachement des compétences au ROME

Jeux annotés utilisés par le notebook `02_competences.ipynb` pour comparer les méthodes de `offres.competences`.

## Items de compétences

- **Échantillon** : 400 occurrences d'items tirées au hasard (graine 2026) parmi les 657 000 items découpés dans les
  textes « compétences attendues » des offres du service public, soit 321 formes distinctes. `poids` = nombre de tirages
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
- **Reclassement par LLM** : une troisième instance choisit, pour chaque item, la meilleure des 10 propositions de la
  méthode hybride (ou aucune). Ses choix absents du pool ont été annotés à l'aveugle par une quatrième instance, mêlés à
  des propositions déjà annotées (accord avec les verdicts existants : kappa 0,83). Biais possible : le reclasseur et les
  annotateurs sont des modèles de la même famille.

Fichiers :

| Fichier | Contenu |
|---|---|
| `competences_items.csv` | les 321 formes : item, forme, poids, est_competence, annotateurs |
| `competences_propositions.csv` | une ligne par (item, méthode) : proposition ROME, score, verdict |
| `metiers_propositions.csv` | une ligne par (métier, méthode) : appellation et fiche ROME proposées, verdict |
| `annotations_brutes.json` | verdicts de chaque annotateur (lots A, B, C et métiers) |

## Métiers

100 métiers de la fonction publique (les 60 plus fréquents, 62 % des offres, et 40 tirés au hasard parmi les autres),
rapprochés des 13 855 appellations du ROME par cinq méthodes. Le verdict porte sur la **fiche ROME** obtenue : `correct` si
ses compétences s'appliquent pour l'essentiel au métier, `partiel` pour une fiche voisine, `faux` sinon. Une seule
annotatrice (instance de Claude).

Les scripts qui ont produit ces fichiers sont dans `scripts/evaluation/` (ils demandent les modèles d'embeddings et
plusieurs minutes de calcul ; le notebook, lui, ne lit que les CSV).
