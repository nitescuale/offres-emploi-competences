# Recalcule les propositions de chaque méthode avec le code actuel (découpage, nettoyage, catalogue), liste celles qui
# n'ont pas encore de verdict, et écrit les candidats de l'hybride e5 (méthode en production) pour le reclassement par LLM.
import sys, json, random
import numpy as np, polars as pl
from offres import competences as c
from offres.embeddings import Modele
S = sys.argv[1]
ech = pl.read_parquet(f'{S}/echantillon.parquet').sort('forme')
cat = c.catalogue_rome()
ancien = pl.read_parquet(f'{S}/catalogue.parquet')
assert cat['code_ogr'].to_list() == ancien['code_ogr'].to_list()
items = ech['item'].to_list()
propres = [c.nettoyer(i) for i in items]
ref = {int(k): v for k, v in json.load(open(f'{S}/annot/reference.json')).items()}
sc = {}
tf = c.Rapprocheur(cat, 'tfidf')
sc['tfidf'] = (tf.vect.transform([c.normaliser(i) for i in items]) @ tf.matrice.T).toarray()
for nom in ['e5', 'minilm']:
    q = Modele(nom).encoder(propres, requete=True)
    sc['e5_asym' if nom == 'e5' else 'minilm'] = q @ np.load(f'{S}/catalogue_{nom}.npy').T
    if nom == 'e5':
        sc['e5'] = q @ np.load(f'{S}/catalogue_e5q.npy').T
z = lambda m: (m - m.mean(1, keepdims=True)) / m.std(1, keepdims=True)
sc['hybride_e5'] = z(sc['e5']) + z(sc['tfidf'])
sc['hybride_minilm'] = z(sc['minilm']) + z(sc['tfidf'])
np.savez_compressed(f'{S}/scores_echantillon3.npz', **sc)
codes = cat['code_ogr'].to_list(); libs = cat['libelle'].to_list(); types = cat['type'].to_list()
dico = c.Rapprocheur(cat, 'dictionnaire').candidats(items)
props = []
for nom, m in sc.items():
    for i in range(len(items)):
        j = int(np.argmax(m[i]))
        props.append({'id': i, 'methode': nom, 'code_ogr': codes[j], 'libelle_rome': libs[j], 'score': float(m[i, j])})
for i in range(len(items)):
    j = dico[i][0][0] if dico[i] else None
    props.append({'id': i, 'methode': 'dictionnaire', 'code_ogr': codes[j] if j is not None else None,
                  'libelle_rome': libs[j] if j is not None else None, 'score': 1.0 if j is not None else None})
props = pl.DataFrame(props)
props.write_parquet(f'{S}/propositions3.parquet')
manque = {}
for p in props.drop_nulls('code_ogr').iter_rows(named=True):
    if p['code_ogr'] not in ref[p['id']]['v']:
        manque.setdefault(p['id'], set()).add(p['code_ogr'])
print('items dont la forme a changé :', sum(c.normaliser(i) != f for i, f in zip(items, ech['forme'])))
print('propositions sans verdict :', sum(map(len, manque.values())), 'sur', len(manque), 'items')
# Lot à annoter : propositions nouvelles mêlées à des leurres déjà annotés (deux par item), ordre aléatoire
random.seed(11)
lot = []
for i, nouveaux in sorted(manque.items()):
    connus = random.sample(sorted(ref[i]['v']), min(2, len(ref[i]['v'])))
    js = [codes.index(x) for x in nouveaux | set(connus)]
    random.shuffle(js)
    lot.append({'id': i, 'item': items[i], 'candidats': [{'code': codes[j], 'libelle': libs[j], 'type': types[j]} for j in js]})
json.dump(lot, open(f'{S}/annot/lot_D.json', 'w'), ensure_ascii=False, indent=0)
# Candidats pour le reclassement : top 10 de l'hybride e5, comme en production
top = np.argsort(-sc['hybride_e5'], axis=1)[:, :c.CANDIDATS]
json.dump([{'id': i, 'item': items[i], 'candidats': [{'code': codes[j], 'libelle': libs[j]} for j in top[i]]}
           for i in range(len(items))], open(f'{S}/reclassement_candidats_e5.json', 'w'), ensure_ascii=False, indent=0)
