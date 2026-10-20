"""Les données du site (dossier `site/`) : tableau de bord par métier et territoire, outil « colle une offre ou ton CV »
et figures de l'article.

Le site est statique : des pages HTML qui lisent des fichiers JSON, sans serveur. `construire` assemble le tout dans
un dossier prêt à publier sur GitHub Pages ; le workflow « Site » le reconstruit après chaque mise à jour des
compétences.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
from datetime import date, timedelta
from pathlib import Path

import polars as pl

from offres import competences, donnees, recrutement
from offres.collecte import maintenant

RACINE = Path(__file__).resolve().parents[2]
DEBUT = date(2022, 1, 1)  # le fichier 2021 ne couvre que quelques semaines
MIN_TEXTES = 30  # en dessous, les compétences citées dans les offres d'un métier ne sont pas montrées
TOP_COMPETENCES = 20
FORMES_MIN = 2  # formes vues au moins deux fois : reprises telles quelles dans l'outil (méthode publiée)
# Compétences citées par au moins 5 % des annonces avec un texte (rigueur, travail en équipe...) : l'outil ne s'en sert pas
# pour trouver les fiches métier proches, où le ROME les attache à quelques fiches seulement et leur donnerait trop de poids
PART_TRANSVERSALE = 0.05

REGIONS = {
    "Auvergne-Rhône-Alpes": "01 03 07 15 26 38 42 43 63 69 73 74",
    "Bourgogne-Franche-Comté": "21 25 39 58 70 71 89 90",
    "Bretagne": "22 29 35 56",
    "Centre-Val de Loire": "18 28 36 37 41 45",
    "Corse": "2A 2B",
    "Grand Est": "08 10 51 52 54 55 57 67 68 88",
    "Hauts-de-France": "02 59 60 62 80",
    "Île-de-France": "75 77 78 91 92 93 94 95",
    "Normandie": "14 27 50 61 76",
    "Nouvelle-Aquitaine": "16 17 19 23 24 33 40 47 64 79 86 87",
    "Occitanie": "09 11 12 30 31 32 34 46 48 65 66 81 82",
    "Pays de la Loire": "44 49 53 72 85",
    "Provence-Alpes-Côte d'Azur": "04 05 06 13 83 84",
    "Outre-mer": "971 972 973 974 975 976 977 978 986 987 988",
}
OUTRE_MER = {
    "971": "Guadeloupe", "972": "Martinique", "973": "Guyane", "974": "La Réunion", "975": "Saint-Pierre-et-Miquelon",
    "976": "Mayotte", "977": "Saint-Barthélemy", "978": "Saint-Martin", "986": "Wallis-et-Futuna",
    "987": "Polynésie française", "988": "Nouvelle-Calédonie",
}
CATEGORIES = ["A+", "A", "B", "C"]


def ecrire(chemin: Path, contenu) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(contenu, ensure_ascii=False, separators=(",", ":")))


def carte_departements(geojson: Path) -> dict:
    """Contours simplifiés des départements de métropole (GeoJSON) → chemins SVG, en projection équirectangulaire
    corrigée de la latitude moyenne. Sert une fois, pour produire `site/geo/departements.json`."""
    geo = json.loads(geojson.read_text())
    lon0, lat0, cos = -5.2, 51.2, math.cos(math.radians(46.5))
    echelle = 1000 / ((9.7 - lon0) * cos)

    def point(lon, lat):
        return round((lon - lon0) * cos * echelle, 1), round((lat0 - lat) * echelle, 1)

    chemins = {}
    for f in geo["features"]:
        polygones = f["geometry"]["coordinates"]
        if f["geometry"]["type"] == "Polygon":
            polygones = [polygones]
        morceaux = []
        for polygone in polygones:
            for anneau in polygone:
                pts = []
                for lon, lat in anneau:
                    p = point(lon, lat)
                    if not pts or p != pts[-1]:
                        pts.append(p)
                if len(pts) >= 4:
                    morceaux.append("M" + "L".join(f"{x:g},{y:g}" for x, y in pts) + "Z")
        chemins[f["properties"]["code"]] = {"nom": f["properties"]["nom"], "d": "".join(morceaux)}
    hauteur = max(float(y) for c in chemins.values() for y in re.findall(r",(-?[\d.]+)", c["d"]))
    return {"source": "france-geojson (Grégoire David), d'après IGN Admin Express, Licence Ouverte",
            "largeur": 1000, "hauteur": math.ceil(hauteur), "departements": chemins}


def territoires() -> dict:
    """Départements (nom, région) et régions, pour les filtres et la carte."""
    carte = json.loads((RACINE / "site" / "geo" / "departements.json").read_text())["departements"]
    noms = {code: d["nom"] for code, d in carte.items()} | OUTRE_MER
    departements = {}
    for region, codes in REGIONS.items():
        for code in codes.split():
            departements[code] = {"nom": noms[code], "region": region}
    return {"regions": list(REGIONS), "departements": dict(sorted(departements.items()))}


def _mois(colonne: str = "date_publication") -> pl.Expr:
    return (pl.col(colonne).dt.year() - DEBUT.year) * 12 + pl.col(colonne).dt.month() - 1


CONNUS = [d for codes in REGIONS.values() for d in codes.split()]


def _dep() -> pl.Expr:
    """Département de la liste, « ? » sinon (non renseigné, étranger, code inconnu)."""
    return pl.when(pl.col("departement").is_in(CONNUS)).then(pl.col("departement")).otherwise(pl.lit("?"))


def identifiant(metier: str) -> str:
    """Identifiant stable d'un métier (empreinte de son nom) : les liens partagés du tableau de bord (#m=...) restent
    valables d'une semaine à l'autre, même quand l'ordre des métiers change."""
    return hashlib.sha1(metier.encode()).hexdigest()[:8]


def offres_du_site(offres: pl.DataFrame, metiers: pl.DataFrame) -> pl.DataFrame:
    """Une ligne par offre depuis 2022 : identifiant du métier, département connu (« ? » sinon), mois, année, champs des
    indicateurs."""
    return (
        offres.filter(pl.col("date_publication") >= DEBUT)
        .join(metiers.select("metier", "id"), on="metier", how="left")
        .with_columns(
            id=pl.col("id").fill_null(""),
            dep=_dep(),
            mois=_mois(),
            annee=pl.col("date_publication").dt.year(),
        )
    )


def _indicateurs(lignes: pl.DataFrame, cles: list[str]) -> pl.DataFrame:
    """Comptes par clé : offres, télétravail (oui / renseigné), catégories, management (oui / renseigné)."""
    return lignes.group_by(cles).agg(
        n=pl.len(),
        tt=pl.col("teletravail").sum(), tt_r=pl.col("teletravail").count(),
        **{f"cat_{c}": (pl.col("categorie") == c).sum() for c in CATEGORIES},
        mg=pl.col("management").sum(), mg_r=pl.col("management").count(),
    )


def _republication(rep: pl.DataFrame, cles: list[str]) -> pl.DataFrame:
    return rep.group_by(cles).agg(rep=pl.col("republiee").sum(), rep_r=pl.len())


COLONNES_KPI = ["n", "tt", "tt_r", *[f"cat_{c}" for c in CATEGORIES], "mg", "mg_r", "rep", "rep_r"]


def _par_territoire(ind: pl.DataFrame, rep: pl.DataFrame, nb_mois: int, series: pl.DataFrame) -> dict:
    """{dep: {"serie": [offres par mois], "annees": {année: [indicateurs]}}} pour un métier (ou tous)."""
    kpi = ind.join(rep, on=["dep", "annee"], how="full", coalesce=True).fill_null(0).sort("dep", "annee")
    resultat: dict[str, dict] = {}
    for ligne in kpi.iter_rows(named=True):
        resultat.setdefault(ligne["dep"], {"serie": [0] * nb_mois, "annees": {}})["annees"][str(ligne["annee"])] = [
            int(ligne[c]) for c in COLONNES_KPI
        ]
    for dep, mois, n in series.iter_rows():
        if 0 <= mois < nb_mois:
            resultat.setdefault(dep, {"serie": [0] * nb_mois, "annees": {}})["serie"][mois] = int(n)
    return resultat


def _competences_citees(textes: pl.DataFrame, libelles: dict[str, tuple[str, str]]) -> dict:
    """Compétences ROME les plus citées dans les offres (part des annonces avec un texte), et part de l'employeur le plus
    présent : un métier dont les textes viennent surtout d'un employeur reflète ses fiches de poste."""
    n = textes["annonce_id"].n_unique()
    if n < MIN_TEXTES:
        return {"textes": n}
    top = (textes.group_by("code_ogr").agg(a=pl.col("annonce_id").n_unique())
           .sort(["a", "code_ogr"], descending=[True, False]).head(TOP_COMPETENCES))
    employeurs = textes.unique("annonce_id").group_by("organisme").len().sort(["len", "organisme"], descending=[True, False])
    return {
        "textes": n,
        "employeur": employeurs["organisme"][0], "part_employeur": round(employeurs["len"][0] / n, 3),
        "liste": [[*libelles[c], round(a / n, 4)] for c, a in top.iter_rows()],
    }


def metiers_frequents(lignes: pl.DataFrame, n: int = 12) -> dict:
    """Les métiers les plus fréquents par territoire (France, région, département) et par année (ou toutes) : clés
    « territoire|année » lues par le tableau de bord quand aucun métier n'est choisi."""
    region = {d: r for r, codes in REGIONS.items() for d in codes.split()}
    base = (lignes.filter(pl.col("id") != "").group_by("id", "dep", "annee").len()
            .with_columns(region=pl.concat_str(pl.lit("r:"), pl.col("dep").replace_strict(region, default=None))))
    resultat = {}
    for cle_t, filtre in [("France", pl.lit(True)), ("region", pl.col("region").is_not_null()), ("dep", pl.col("dep") != "?")]:
        t = {"France": pl.lit("France"), "region": pl.col("region"), "dep": pl.col("dep")}[cle_t]
        sous = base.filter(filtre).with_columns(t=t)
        for annee in [None, *sorted(base["annee"].unique().to_list())]:
            g = (sous if annee is None else sous.filter(pl.col("annee") == annee)).group_by("t", "id").agg(pl.col("len").sum())
            g = g.sort(["t", "len", "id"], descending=[False, True, False]).group_by("t", maintain_order=True).head(n)
            for (terr,), lot in g.group_by("t", maintain_order=True):
                resultat[f"{terr}|{annee or 'toutes'}"] = [[i, int(c)] for i, c in lot.select("id", "len").iter_rows()]
    return resultat


def domaine(ligne: dict) -> str:
    if ligne["type"] == "Savoir":
        return f"Savoirs · {ligne['sous_type']}" if ligne["sous_type"] else "Savoirs"
    return ligne["domaine_competence"] or ligne["type"]


def donnees_tableau(sortie: Path, offres: pl.DataFrame, formes: pl.DataFrame, items: pl.DataFrame,
                    metiers_rome: pl.DataFrame, catalogue: pl.DataFrame, par_fiche: pl.DataFrame) -> dict:
    """Fichiers du tableau de bord : `metiers.json` (liste), `metiers/<id>.json` (un par métier, 0 = tous) et
    `resume.json` ; renvoie le résumé."""
    fin = offres["date_publication"].max()
    # Le dernier mois n'est gardé que s'il est (presque) complet
    nb_mois = (fin.year - DEBUT.year) * 12 + fin.month - (1 if fin.day < 25 else 0)
    metiers = (offres.filter(pl.col("date_publication") >= DEBUT).drop_nulls("metier").group_by("metier").len()
               .sort(["len", "metier"], descending=[True, False])
               .with_columns(id=pl.col("metier").map_elements(identifiant, return_dtype=pl.Utf8)))
    if metiers["id"].n_unique() < metiers.height:
        raise ValueError("deux métiers ont le même identifiant : allonger l'empreinte")
    lignes = offres_du_site(offres, metiers)
    rep = (recrutement.republications(offres).join(metiers.select("metier", "id"), on="metier", how="left")
           .with_columns(id=pl.col("id").fill_null(""), dep=_dep(), annee=pl.col("date_publication").dt.year()))

    libelles = {r["code_ogr"]: (r["libelle"], domaine(r)) for r in catalogue.iter_rows(named=True)}
    textes = (items.join(formes.select("forme", "code_ogr"), on="forme").drop_nulls("code_ogr")
              .join(offres.filter(pl.col("date_publication") >= DEBUT).unique("annonce_id")
                    .select("annonce_id", "metier", "organisme"), on="annonce_id")
              .join(metiers.select("metier", "id"), on="metier", how="left")
              .select("annonce_id", "id", "organisme", "code_ogr").unique(["annonce_id", "code_ogr"]))
    fiches = metiers_rome.select("metier", "code_rome", "libelle_rome", "appellation")
    coeur = (par_fiche.filter(pl.col("coeur")).join(catalogue.select("code_ogr", "libelle"), on="code_ogr")
             .sort("code_rome", "libelle").group_by("code_rome", maintain_order=True).agg(pl.col("libelle")))
    coeur = dict(zip(coeur["code_rome"], coeur["libelle"].to_list()))

    ind = _indicateurs(lignes, ["id", "dep", "annee"])
    rp = _republication(rep, ["id", "dep", "annee"])
    series = lignes.group_by("id", "dep", "mois").len()
    # Tous les métiers : mêmes comptes sans la clé du métier
    ind_tous, rp_tous = _indicateurs(lignes, ["dep", "annee"]), _republication(rep, ["dep", "annee"])
    series_tous = lignes.group_by("dep", "mois").len()

    def fichier(id_, ind_m, rp_m, series_m, textes_m, fiche, **autres):
        contenu = {"territoires": _par_territoire(ind_m, rp_m, nb_mois, series_m),
                   "competences": _competences_citees(textes_m, libelles), **autres}
        if fiche:
            contenu["fiche"] = {**fiche, "coeur": coeur.get(fiche["code_rome"], [])}
        ecrire(sortie / "metiers" / f"{id_}.json", contenu)

    fichier("tous", ind_tous, rp_tous, series_tous, textes, None, metiers_frequents=metiers_frequents(lignes))
    groupes = {k[0]: g.drop("id") for k, g in ind.group_by("id")}
    groupes_rp = {k[0]: g.drop("id") for k, g in rp.group_by("id")}
    groupes_s = {k[0]: g.drop("id") for k, g in series.group_by("id")}
    groupes_t = {k[0]: g for k, g in textes.group_by("id")}
    vide_rp = rp_tous.clear()
    fiches_d = {r["metier"]: r for r in fiches.iter_rows(named=True)}
    liste = []
    for id_, metier, n in metiers.select("id", "metier", "len").iter_rows():
        f = fiches_d.get(metier)
        fiche = ({"code_rome": f["code_rome"], "libelle": f["libelle_rome"], "appellation": f["appellation"]}
                 if f and f["code_rome"] else None)
        t = groupes_t.get(id_, textes.clear())
        fichier(id_, groupes[id_], groupes_rp.get(id_, vide_rp), groupes_s[id_], t, fiche)
        liste.append([id_, metier, n, t["annonce_id"].n_unique(), fiche["code_rome"] if fiche else None])
    ecrire(sortie / "metiers.json", {"colonnes": ["id", "metier", "offres", "textes", "code_rome"], "lignes": liste})

    resume = {
        "mise_a_jour": maintenant().date().isoformat(),
        "debut": DEBUT.isoformat(), "fin": fin.isoformat(), "nb_mois": nb_mois,
        "offres": lignes.height, "metiers": metiers.height,
        "textes": int(textes["annonce_id"].n_unique()),
        "republication_fin": (fin - timedelta(days=recrutement.MAX_JOURS)).isoformat(),
        "colonnes_kpi": COLONNES_KPI,
    }
    ecrire(sortie / "resume.json", resume)
    return resume


def donnees_outil(sortie: Path, formes: pl.DataFrame, items: pl.DataFrame, catalogue: pl.DataFrame, par_fiche: pl.DataFrame,
                  metiers_rome: pl.DataFrame, metiers: pl.DataFrame, noms_fiches: dict[str, str] | None = None) -> None:
    """Fichiers de l'outil : le catalogue ROME (l'index TF-IDF est construit dans le navigateur à partir des libellés),
    les formes déjà vues dans les offres avec leur rattachement par la méthode publiée, et les fiches métier."""
    lignes = catalogue.to_dicts()
    domaines = sorted({domaine(r) for r in lignes})
    indice = {r["code_ogr"]: i for i, r in enumerate(lignes)}
    citees = items.join(formes.select("forme", "code_ogr"), on="forme").drop_nulls("code_ogr")
    parts = citees.group_by("code_ogr").agg(pl.col("annonce_id").n_unique() / items["annonce_id"].n_unique())
    transversales = sorted(indice[c] for c, p in parts.iter_rows() if p >= PART_TRANSVERSALE and c in indice)
    ecrire(sortie / "catalogue.json", {
        "libelles": [r["libelle"] for r in lignes],
        "domaines": domaines,
        "domaine": [domaines.index(domaine(r)) for r in lignes],
        "macro": [r["libelle_macro_competence"] for r in lignes],
        "transversales": transversales,
    })
    vues = formes.filter(pl.col("occurrences") >= FORMES_MIN, pl.col("code_ogr").is_in(list(indice))).sort("forme")
    ecrire(sortie / "formes.json", {
        "formes": vues["forme"].to_list(),
        "entrees": [indice[c] for c in vues["code_ogr"]],
        "occurrences": vues["occurrences"].to_list(),
    })
    # Métiers de la fonction publique rattachés à chaque fiche, pour renvoyer vers le tableau de bord
    ids = dict(zip(metiers["metier"], metiers["id"]))
    fp = (metiers_rome.filter(pl.col("metier").is_in(list(ids))).sort("offres", descending=True)
          .group_by("code_rome", maintain_order=True).agg(pl.col("metier").head(3)))
    fp = {c: [[ids[m], m] for m in ms] for c, ms in fp.iter_rows()}
    fiches = []
    noms = noms_fiches or dict(donnees.rome("referentiel_code_rome").select("code_rome", "libelle_rome").iter_rows())
    for (code,), g in par_fiche.filter(pl.col("code_ogr").is_in(list(indice))).sort("code_rome", "code_ogr").group_by(
            "code_rome", maintain_order=True):
        fiches.append([code, noms.get(code, code),
                       [indice[c] for c in g.filter(pl.col("coeur"))["code_ogr"]],
                       [indice[c] for c in g.filter(~pl.col("coeur"))["code_ogr"]],
                       fp.get(code, [])])
    ecrire(sortie / "fiches.json", {"colonnes": ["code_rome", "libelle", "coeur", "autres", "metiers"], "lignes": fiches})


def construire(sortie: Path) -> dict:
    """Site complet dans `sortie` : pages, scripts, données et figures."""
    if sortie.exists():
        shutil.rmtree(sortie)
    shutil.copytree(RACINE / "site", sortie)
    shutil.copytree(RACINE / "rapports" / "figures", sortie / "figures")
    offres = donnees.offres_service_public()
    formes = pl.read_parquet(donnees.chemin("competences_formes.parquet"))
    items = pl.read_parquet(donnees.chemin("competences_items.parquet"))
    metiers_rome = pl.read_parquet(donnees.chemin("metiers_rome.parquet"))
    catalogue = competences.catalogue_rome()
    par_fiche = competences.competences_par_fiche()
    ecrire(sortie / "donnees" / "territoires.json", territoires())
    resume = donnees_tableau(sortie / "donnees", offres, formes, items, metiers_rome, catalogue, par_fiche)
    metiers = pl.DataFrame(json.loads((sortie / "donnees" / "metiers.json").read_text())["lignes"],
                           schema=["id", "metier", "offres", "textes", "code_rome"], orient="row")
    donnees_outil(sortie / "outil", formes, items, catalogue, par_fiche, metiers_rome, metiers)
    return resume
