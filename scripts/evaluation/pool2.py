import sys, json, random
import numpy as np, polars as pl
from offres import competences as c
S = sys.argv[1]
ech = pl.read_parquet(f'{S}/echantillon.parquet').sort('forme')
cat = pl.read_parquet(f'{S}/catalogue.parquet')
sc = dict(np.load(f'{S}/scores_echantillon.npz'))
z = lambda m: (m - m.mean(1, keepdims=True)) / m.std(1, keepdims=True)
sc['hybride_e5'] = z(sc['e5_sym']) + z(sc['tfidf'])
sc['hybride_minilm'] = z(sc['minilm']) + z(sc['tfidf'])
np.savez_compressed(f'{S}/scores_echantillon2.npz', **sc)
items = ech['item'].to_list()
dico = c.Rapprocheur(cat, 'dictionnaire').candidats(items)
libs = cat['libelle'].to_list(); types = cat['type'].to_list()
random.seed(7)
pool = []
for i, item in enumerate(items):
    js = {int(np.argmax(m[i])) for m in sc.values()} | {j for j, _ in dico[i]}
    js = sorted(js); random.shuffle(js)
    pool.append({'id': i, 'item': item, 'candidats': [{'code': cat['code_ogr'][j], 'libelle': libs[j], 'type': types[j]} for j in js]})
print(len(pool), sum(len(p['candidats']) for p in pool))
json.dump(pool, open(f'{S}/pool.json', 'w'), ensure_ascii=False, indent=0)
