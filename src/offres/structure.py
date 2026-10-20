"""Structure du marché à partir des compétences écrites dans les offres : compétences transversales ou de métier,
réseau de cooccurrence, familles de métiers (NMF sur les profils de compétences).

Les fonctions prennent les items `(annonce_id, forme)` de `offres.competences.items_des_offres` et le métier de chaque
annonce ; elles ne dépendent ni des modèles d'embeddings ni du réseau.
"""

from __future__ import annotations

import networkx as nx
import numpy as np
import polars as pl
from scipy import sparse
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfTransformer
from sklearn.metrics import adjusted_rand_score

from offres.competences import _TITRE

# Une compétence citée pour plus d'un quart des métiers est « transversale » : elle ne dit rien du métier. Un métier ne
# « cite » une compétence que si au moins 2 % de ses annonces la mentionnent, sans quoi les gros métiers, qui ont plus
# de textes, citeraient tout une fois et feraient passer pour transversales des compétences de quelques métiers.
SEUIL_TRANSVERSAL = 0.25
PART_MIN_METIER = 0.02


def items_par_metier(items: pl.DataFrame, offres: pl.DataFrame, min_annonces: int = 20) -> pl.DataFrame:
    """Items des annonces dont le métier a au moins `min_annonces` textes de compétences ; sans les restes de rubriques
    (« compétences », « connaissances et expériences ») que le découpage a laissé passer."""
    metier = offres.filter(pl.col("competences_texte").is_not_null()).unique("annonce_id").select("annonce_id", "metier")
    x = (items.unique(["annonce_id", "forme"]).join(metier, on="annonce_id").drop_nulls("metier")
         .filter(~pl.col("forme").str.contains(_TITRE.pattern)))
    gardes = x.group_by("metier").agg(pl.col("annonce_id").n_unique().alias("n")).filter(pl.col("n") >= min_annonces)
    return x.filter(pl.col("metier").is_in(gardes["metier"].implode()))


def transversalite(x: pl.DataFrame, part_min: float = PART_MIN_METIER) -> pl.DataFrame:
    """Par forme : nombre d'annonces, nombre de métiers qui la citent (dans au moins `part_min` de leurs annonces) et
    part de ces métiers parmi tous."""
    n_metiers = x["metier"].n_unique()
    taille = x.group_by("metier").agg(n=pl.col("annonce_id").n_unique())
    par_metier = (x.group_by("forme", "metier").agg(a=pl.col("annonce_id").n_unique()).join(taille, on="metier")
                  .with_columns(cite=pl.col("a") / pl.col("n") >= part_min))
    return (par_metier.group_by("forme").agg(annonces=pl.col("a").sum(), metiers=pl.col("cite").sum())
            .with_columns(part_metiers=pl.col("metiers") / n_metiers,
                          transversale=pl.col("metiers") / n_metiers > SEUIL_TRANSVERSAL)
            .sort(["annonces", "forme"], descending=[True, False]))  # ordre total : `head(n)` reproductible


def cooccurrences(x: pl.DataFrame, formes: list[str], min_paires: int = 20) -> pl.DataFrame:
    """Paires de formes citées dans les mêmes annonces, avec l'information mutuelle ponctuelle normalisée (NPMI, de -1
    à 1 ; 0 = indépendance) : elle corrige l'effet de la fréquence, qui ferait sinon tout relier à « rigueur »."""
    n = x["annonce_id"].n_unique()
    sous = x.filter(pl.col("forme").is_in(formes)).select("annonce_id", "forme")
    freq = sous.group_by("forme").len()
    f = dict(zip(freq["forme"], freq["len"]))
    paires = (sous.join(sous, on="annonce_id").filter(pl.col("forme") < pl.col("forme_right"))
              .group_by("forme", "forme_right").len().filter(pl.col("len") >= min_paires))
    p_ab = pl.col("len") / n
    p_a = pl.col("forme").replace_strict(f) / n
    p_b = pl.col("forme_right").replace_strict(f) / n
    return (paires.with_columns(npmi=(p_ab / (p_a * p_b)).log() / -p_ab.log())
            .rename({"forme": "a", "forme_right": "b", "len": "annonces"}).sort("npmi", descending=True))


def communautes(aretes: pl.DataFrame, seuil_npmi: float = 0.25, graine: int = 1) -> tuple[nx.Graph, list[set[str]]]:
    """Graphe des paires au-dessus du seuil et ses communautés (Louvain), de la plus grande à la plus petite."""
    g = nx.Graph()
    for a, b, w in aretes.filter(pl.col("npmi") >= seuil_npmi).select("a", "b", "npmi").iter_rows():
        g.add_edge(a, b, weight=w)
    groupes = nx.community.louvain_communities(g, weight="weight", seed=graine)
    return g, sorted(groupes, key=len, reverse=True)


def matrice_metiers(x: pl.DataFrame, min_annonces_forme: int = 20) -> tuple[list[str], list[str], sparse.csr_matrix]:
    """Métiers × formes de métier (transversales exclues) : part des annonces du métier qui citent la forme, pondérée
    par TF-IDF pour que les formes propres à peu de métiers comptent plus. Les métiers sans aucune forme du vocabulaire
    sont écartés (la NMF les rangerait arbitrairement dans la première famille)."""
    t = transversalite(x)
    vocab = t.filter(~pl.col("transversale"), pl.col("annonces") >= min_annonces_forme)["forme"].sort().to_list()
    c = x.filter(pl.col("forme").is_in(vocab)).group_by("metier", "forme").len()
    metiers = c["metier"].unique().sort().to_list()
    n_ann = dict(x.group_by("metier").agg(pl.col("annonce_id").n_unique()).iter_rows())
    im = {m: i for i, m in enumerate(metiers)}
    jf = {f: j for j, f in enumerate(vocab)}
    valeurs = (c["len"] / c["metier"].replace_strict(n_ann)).to_numpy()
    m = sparse.csr_matrix((valeurs, ([im[v] for v in c["metier"]], [jf[v] for v in c["forme"]])),
                          shape=(len(metiers), len(vocab)))
    return metiers, vocab, TfidfTransformer().fit_transform(m).tocsr()


def familles(matrice: sparse.csr_matrix, k: int, graine: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """NMF : poids de chaque métier dans chaque famille (W) et poids de chaque forme dans chaque famille (H)."""
    nmf = NMF(k, init="nndsvda", random_state=graine, max_iter=1000)
    return nmf.fit_transform(matrice), nmf.components_


def stabilite(matrice: sparse.csr_matrix, ks: list[int], graines: int = 5) -> pl.DataFrame:
    """Pour chaque k, accord moyen et minimal (indice de Rand ajusté) entre les familles obtenues avec des
    initialisations aléatoires différentes : un découpage qui change à chaque tirage ne décrit pas une structure réelle.
    `familles` part d'une initialisation déterministe (nndsvda) ; ce test mesure donc la stabilité du problème autour
    d'elle, pas la variance d'une procédure qui serait de toute façon reproductible."""
    lignes = []
    for k in ks:
        etiquettes = []
        for g in range(graines):
            w = NMF(k, init="random", random_state=g, max_iter=1000).fit_transform(matrice)
            etiquettes.append(w.argmax(axis=1))
        ari = [adjusted_rand_score(etiquettes[i], etiquettes[j]) for i in range(graines) for j in range(i + 1, graines)]
        lignes.append({"k": k, "ari_moyen": float(np.mean(ari)), "ari_min": float(np.min(ari))})
    return pl.DataFrame(lignes)
