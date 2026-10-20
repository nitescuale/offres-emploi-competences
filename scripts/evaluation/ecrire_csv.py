# Fusionne les verdicts de tous les lots (le plus sévère quand deux annotateurs ont jugé la même proposition) et écrit
# evaluation/competences_items.csv, competences_propositions.csv et annotations_brutes.json.
# Usage : python ecrire_csv.py SCRATCH methode=fichier_de_choix.json ...  (un fichier par reclasseur LLM)
import sys, json
import polars as pl
from offres import competences as c
S = sys.argv[1]
reclasseurs = dict(a.split("=", 1) for a in sys.argv[2:])
rang = {'faux': 0, 'partiel': 1, 'correct': 2}
inv = {v: k for k, v in rang.items()}
lots = {}
for nom in ['A', 'B', 'C', 'D', 'E', 'F']:
    try:
        lots[nom] = json.load(open(f'{S}/annot/verdicts_{nom}.json'))
    except FileNotFoundError:
        pass
ref = {}
for nom, lot in lots.items():
    for d in lot:
        r = ref.setdefault(d['id'], {'est': None, 'v': {}, 'par': set()})
        if nom in 'AB':  # est_competence vient des annotateurs principaux
            r['est'] = d['est_competence'] if r['est'] is None else (r['est'] and d['est_competence'])
            r['par'].add(nom)
        for code, v in d['verdicts'].items():
            r['v'][code] = min(r['v'].get(code, 2), rang[v]) if nom in 'AB' else r['v'].get(code, rang[v])
ech = pl.read_parquet(f'{S}/echantillon.parquet').sort('forme')
props = pl.read_parquet(f'{S}/propositions3.parquet')
lignes = props.drop_nulls('code_ogr').to_dicts()
cat = c.catalogue_rome()
libelle = dict(zip(cat['code_ogr'], cat['libelle']))
for methode, fichier in reclasseurs.items():
    for d in json.load(open(fichier)):
        if d['code']:
            lignes.append({'id': d['id'], 'methode': methode, 'code_ogr': d['code'], 'libelle_rome': libelle[d['code']], 'score': None})
p = pl.DataFrame(lignes).with_columns(
    verdict=pl.struct('id', 'code_ogr').map_elements(lambda r: inv[ref[r['id']]['v'][r['code_ogr']]], return_dtype=pl.Utf8))
items = pl.DataFrame({
    'id': range(len(ech)), 'item': ech['item'], 'forme': [c.normaliser(i) for i in ech['item']], 'poids': ech['poids'],
    'est_competence': [ref[i]['est'] for i in range(len(ech))],
    'annotateurs': ['+'.join(sorted(ref[i]['par'])) for i in range(len(ech))]})
items.write_csv('evaluation/competences_items.csv')
p.sort('id', 'methode').write_csv('evaluation/competences_propositions.csv')
brutes = json.load(open('evaluation/annotations_brutes.json'))
brutes.update(lots)
json.dump(brutes, open('evaluation/annotations_brutes.json', 'w'), ensure_ascii=False, indent=0)
print(items.height, p.height); print(p['methode'].value_counts().sort('methode'))
