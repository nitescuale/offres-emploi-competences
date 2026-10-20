# Dictionnaire des données : `csp_offres.parquet`

Une ligne par offre (référence) publiée sur [Choisir le service public](https://choisirleservicepublic.gouv.fr/), du 1er janvier 2022 à la dernière mise à jour du jeu de données. Produit par `offres csp` (`src/offres/csp.py`) à partir du jeu [« Les offres diffusées sur Choisir le service public »](https://www.data.gouv.fr/datasets/les-offres-diffusees-sur-choisir-le-service-public), DGAFP, **Licence Ouverte 2.0**. Le fichier dérivé est publié sous la même licence, avec mention de la source.

Taux de remplissage mesurés sur la version d'octobre 2026 (1 621 178 offres).

| Colonne | Type | Rempli | Contenu |
|---|---|---|---|
| `reference` | texte | 100 % | identifiant de l'offre (unique) |
| `organisme` | texte | 100 % | organisme de rattachement (communes, ministères, CHU, CNRS...) |
| `versant` | texte | 99,5 % | État, territoriale ou hospitalière ; complété par l'organisme quand celui-ci n'a qu'un versant |
| `employeur` | texte | 24 % | employeur précis (rare) |
| `metier` | texte | 100 % | métier du répertoire de la fonction publique, libellé harmonisé (astérisques, apostrophes) ; 885 métiers |
| `intitule` | texte | 100 % | intitulé libre de l'annonce |
| `categorie_libelle`, `categorie` | texte | 98,7 % | catégorie statutaire ; `categorie` vaut A+, A, B ou C |
| `statut_poste` | texte | 97,6 % | « Vacant » ou « Susceptible d'être vacant » (les valeurs égarées comme « Cadre » sont vidées) |
| `nature_emploi` | texte | 99,9 % | ouvert aux titulaires et contractuels, réservé aux fonctionnaires, contractuels seulement |
| `nature_contrat`, `duree_contrat` | texte | 8-10 % | CDD et sa durée, quand précisés |
| `localisation` | texte | 98,6 % | département tel qu'écrit dans la source, par ex. « Cher (18 ) » |
| `departement`, `departement_nom` | texte | 99,2 % | code (01-95, 2A, 2B, 971-988) ; retrouvé par le code postal du lieu d'affectation quand la localisation manque |
| `lieu_affectation`, `commune` | texte | 88 %, 96 % | adresse et commune du poste |
| `niveau_etudes_libelle`, `niveau_etudes` | texte, entier | 12,7 % | niveau de diplôme demandé (1 à 8, nomenclature européenne) |
| `experience` | texte | 24,9 % | Débutant, Confirmé, Expert |
| `specialisation` | texte | 3,7 % | domaine(s) de diplôme ; plusieurs valeurs jointes par « \| » |
| `teletravail`, `management`, `temps_plein` | booléen | 41 %, 44 %, 86 % | **vide ne veut pas dire non** : le champ est facultatif |
| `langues`, `langues_niveaux` | texte | 3,8 % | langues demandées et niveaux, jointes par « \| » |
| `date_publication` | date | 100 % | première publication |
| `date_debut_publication`, `date_fin_publication` | date | 96 % | fenêtre de publication par défaut |
| `date_vacance` | date | 97 % | date à laquelle le poste est libre |
| `competences_texte` | texte | 4,5 % | « compétences attendues », texte libre ; **presque absent dans la territoriale** (13 % des offres de l'État, 10 % à l'hôpital) |
| `documents`, `avis_jo` | texte | 14 %, 2 % | pièces à fournir, avis de vacance au Journal officiel |
| `annonce_id` | entier | 100 % | empreinte de tous les champs sauf la référence : des références différentes avec le même `annonce_id` sont une même annonce multi-postes |
| `postes_annonce` | entier | 100 % | nombre de références partageant cette annonce |
| `fichier_source` | texte | 100 % | date de mise à jour et titre du fichier annuel d'origine |

## Pièges connus

- **Lignes éclatées dans la source** : une offre à plusieurs spécialisations ou langues y occupe plusieurs lignes ; elles sont regroupées ici.
- **Annonces multi-postes** : environ 41 000 lignes dupliquent une autre annonce à la référence près (par exemple 210 postes d'agent d'accompagnement de l'enfant publiés le même jour par une commune). Pour compter des annonces plutôt que des postes, dédoublonner sur `annonce_id`.
- **Dates aberrantes** : les années hors de 2015-2030 (fautes de frappe : 1922, 2926, 31/12/9999) sont vidées ; environ 670 valeurs.
- **Pas de salaire** dans cette source.
- **2026 est partiel** : le fichier s'arrête à sa dernière mise à jour (fin septembre 2026).
