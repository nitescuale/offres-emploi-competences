import sys, json
import numpy as np, polars as pl
from offres import competences as c
S = sys.argv[1]
A = {d['id']: d for d in json.load(open(f'{S}/annot/verdicts_A.json'))}
B = {d['id']: d for d in json.load(open(f'{S}/annot/verdicts_B.json'))}
rang = {'faux': 0, 'partiel': 1, 'correct': 2}
# Accord sur le recouvrement
comm = sorted(set(A) & set(B))
pa, pb = [], []
est_acc = 0
for i in comm:
    est_acc += A[i]['est_competence'] == B[i]['est_competence']
    for code in A[i]['verdicts']:
        pa.append(rang[A[i]['verdicts'][code]]); pb.append(rang[B[i]['verdicts'][code]])
pa, pb = np.array(pa), np.array(pb)
from sklearn.metrics import cohen_kappa_score
print(f'recouvrement {len(comm)} items, {len(pa)} paires ; accord brut {np.mean(pa==pb):.2f}, kappa {cohen_kappa_score(pa,pb):.2f}, '
      f'kappa pondéré {cohen_kappa_score(pa,pb,weights="linear"):.2f}; accord correct-vs-reste {np.mean((pa==2)==(pb==2)):.2f}; est_competence {est_acc}/{len(comm)}')
# Référence : verdict le plus prudent quand les deux ont annoté
ref = {}
for i in set(A) | set(B):
    ds = [d for d in (A.get(i), B.get(i)) if d]
    ref[i] = {'est': all(d['est_competence'] for d in ds),
              'v': {code: min((rang[d['verdicts'][code]] for d in ds)) for code in ds[0]['verdicts']}}
ech = pl.read_parquet(f'{S}/echantillon.parquet').sort('forme')
cat = pl.read_parquet(f'{S}/catalogue.parquet')
codes = cat['code_ogr'].to_list()
sc = dict(np.load(f'{S}/scores_echantillon2.npz'))
items = ech['item'].to_list(); poids = ech['poids'].to_numpy()
dico = c.Rapprocheur(cat, 'dictionnaire').candidats(items)
est = np.array([ref[i]['est'] for i in range(len(items))])
print('items non-compétences (pondéré)', round(1 - poids[est].sum() / poids.sum(), 3))
lignes = []
for nom, m in list(sc.items()) + [('dictionnaire', None)]:
    for i in range(len(items)):
        if m is None:
            j, s = (dico[i][0][0], 1.0) if dico[i] else (None, None)
        else:
            j = int(np.argmax(m[i])); s = float(m[i, j])
        v = ref[i]['v'][codes[j]] if j is not None else None
        lignes.append({'methode': nom, 'id': i, 'poids': int(poids[i]), 'est': bool(est[i]), 'score': s, 'verdict': v})
r = pl.DataFrame(lignes)
r.write_parquet(f'{S}/evaluation.parquet')
oracle = sum(poids[i] for i in range(len(items)) if est[i] and max(ref[i]['v'].values()) == 2) / poids[est].sum()
print('oracle (au moins un candidat correct)', round(oracle, 3))
res = (r.filter('est').group_by('methode').agg(
    couverture=(pl.col('verdict').is_not_null() * pl.col('poids')).sum() / pl.col('poids').sum(),
    correct=((pl.col('verdict') == 2) * pl.col('poids')).sum() / pl.col('poids').sum(),
    correct_ou_partiel=((pl.col('verdict') >= 1) * pl.col('poids')).sum() / pl.col('poids').sum(),
).sort('correct', descending=True))
print(res)
