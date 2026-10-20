import json, sys
import numpy as np, polars as pl
S = sys.argv[1]
rang = {'faux': 0, 'partiel': 1, 'correct': 2}
A = {d['id']: d for d in json.load(open(f'{S}/annot/verdicts_A.json'))}
B = {d['id']: d for d in json.load(open(f'{S}/annot/verdicts_B.json'))}
C = {d['id']: d for d in json.load(open(f'{S}/annot/verdicts_C.json'))}
ref = {}
for i in set(A) | set(B):
    ds = [d for d in (A.get(i), B.get(i)) if d]
    ref[i] = {'est': all(d['est_competence'] for d in ds), 'v': {k: min(rang[d['verdicts'][k]] for d in ds) for k in ds[0]['verdicts']}}
# cohérence de l'annotateur C sur les leurres déjà annotés
a, b = [], []
for i, d in C.items():
    for k, v in d['verdicts'].items():
        if k in ref[i]['v']:
            a.append(rang[v]); b.append(ref[i]['v'][k])
a, b = np.array(a), np.array(b)
from sklearn.metrics import cohen_kappa_score
print(f'leurres {len(a)} : accord {np.mean(a==b):.2f}, kappa {cohen_kappa_score(a,b):.2f}')
for i, d in C.items():
    for k, v in d['verdicts'].items():
        ref[i]['v'].setdefault(k, rang[v])
json.dump({str(k): v for k, v in ref.items()}, open(f'{S}/annot/reference.json', 'w'), ensure_ascii=False)
ech = pl.read_parquet(f'{S}/echantillon.parquet').sort('forme')
poids = ech['poids'].to_numpy()
ch = {d['id']: d['code'] for d in json.load(open(f'{S}/annot/rerank_choix.json'))}
est = np.array([ref[i]['est'] for i in range(len(poids))])
w = poids[est]; ids = np.arange(len(poids))[est]
v = np.array([ref[i]['v'][ch[i]] if ch[i] else -1 for i in ids])
print('LLM : couverture', round(w[v >= 0].sum() / w.sum(), 3), 'correct', round(w[v == 2].sum() / w.sum(), 3),
      'correct_ou_partiel', round(w[v >= 1].sum() / w.sum(), 3),
      '| précision sur les choix : strict', round(w[v == 2].sum() / w[v >= 0].sum(), 3), 'large', round(w[v >= 1].sum() / w[v >= 0].sum(), 3))
# non-compétences : le LLM s'abstient-il ?
nc = [i for i in range(len(poids)) if not est[i]]
print('non-compétences', len(nc), 'abstentions LLM', sum(ch[i] is None for i in nc))
