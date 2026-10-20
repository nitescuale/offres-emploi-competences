# Scores complets des méthodes sur l'échantillon, top-1 de chacune, pool à annoter
import sys, json, random
import numpy as np, polars as pl
from offres import competences as c
from offres.embeddings import Modele
S = sys.argv[1]
ech = pl.read_parquet(f'{S}/echantillon.parquet').sort('forme')
cat = pl.read_parquet(f'{S}/catalogue.parquet')
items = ech['item'].to_list()
propres = [c.nettoyer(i) for i in items]
scores = {}
tf = c.Rapprocheur(cat, 'tfidf')
scores['tfidf'] = (tf.vect.transform([c.normaliser(i) for i in items]) @ tf.matrice.T).toarray()
libs = cat['libelle'].to_list()
for nom in ['e5', 'minilm']:
    m = Modele(nom)
    q = m.encoder(propres, requete=True)
    mat = m.encoder(libs, requete=False)
    np.save(f'{S}/catalogue_{nom}.npy', mat)
    scores[nom] = q @ mat.T
    if nom == 'e5':
        mat_q = m.encoder(libs, requete=True)  # usage symétrique (« query: » des deux côtés)
        np.save(f'{S}/catalogue_e5q.npy', mat_q)
        scores['e5_sym'] = q @ mat_q.T
np.savez_compressed(f'{S}/scores_echantillon.npz', **scores)
dico = c.Rapprocheur(cat, 'dictionnaire').candidats(items)
print('scores calculés', {k: v.shape for k, v in scores.items()})
