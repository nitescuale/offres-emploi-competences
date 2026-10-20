import sys, re
import numpy as np, polars as pl
from offres import donnees, competences as c
from offres.embeddings import Modele
S = sys.argv[1]
t = donnees.offres_service_public()
met = t.group_by('metier').len().sort('len', descending=True).drop_nulls('metier')
app = c.catalogue_appellations()
noms = [c.sans_double_genre(x, True) for x in met['metier'].to_list()]
libs = [c.sans_double_genre(x, False) for x in app['libelle'].to_list()]
sc = {}
tf = c.Rapprocheur(app, 'tfidf')
sc['tfidf'] = (tf.vect.transform([c.normaliser(x) for x in noms]) @ tf.matrice.T).toarray()
for nom, req in [('e5', True), ('minilm', False)]:
    m = Modele(nom)
    sc[nom] = m.encoder([x.lower() for x in noms], requete=True) @ m.encoder([x.lower() for x in libs], requete=req).T
z = lambda m: (m - m.mean(1, keepdims=True)) / m.std(1, keepdims=True)
sc['hybride_e5'] = z(sc['e5']) + z(sc['tfidf'])
sc['hybride_minilm'] = z(sc['minilm']) + z(sc['tfidf'])
np.savez_compressed(f'{S}/scores_metiers.npz', **sc)
out = met
for k, v in sc.items():
    j = v.argmax(1)
    out = out.with_columns(pl.Series(f'{k}_app', app['libelle'].gather(j).to_list()), pl.Series(f'{k}_rome', app['code_rome'].gather(j).to_list()),
                           pl.Series(f'{k}_s', v.max(1)))
out.write_parquet(f'{S}/metiers_rapp.parquet')
print(out.height)
