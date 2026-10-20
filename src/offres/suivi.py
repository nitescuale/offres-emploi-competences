"""Suivi de production : contrôles des données publiées et dérive des compétences demandées.

`controler` vérifie chaque jour les fichiers de la release `donnees` (fraîcheur, volumes, champs manquants, couverture
des compétences) ; un contrôle en « erreur » fait échouer le workflow, ce qui prévient par courriel. `derive` compare les
compétences citées ces six derniers mois aux deux années précédentes, en brut puis à employeurs constants : les offres
de quelques gros employeurs pèsent si lourd que leurs modèles d'annonce suffisent à faire « émerger » une compétence.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import polars as pl

from offres import web

OK, ALERTE, ERREUR = "ok", "alerte", "erreur"
GRAVITE = {OK: 0, ALERTE: 1, ERREUR: 2}

FRAICHEUR_ALERTE, FRAICHEUR_ERREUR = 45, 75  # jours depuis la dernière offre publiée (le fichier de l'année est mensuel)
BAISSE_VOLUME = 0.95  # moins d'offres qu'au contrôle précédent : un fichier annuel a sauté
ECART_MOIS = (0.6, 1.6)  # dernier mois complet comparé au même mois un an plus tôt
HAUSSE_MANQUANTS = 0.05  # part de valeurs manquantes : +5 points sur trois mois par rapport aux douze précédents
BAISSE_TEXTES = 0.6  # part d'offres avec un texte de compétences : divisée par plus de 1/0,6
PART_CONTRIBUTEUR, TARISSEMENT = 0.02, 0.25  # employeur auteur d'au moins 2 % des textes, qui en écrit 4 fois moins
COUVERTURE_ALERTE, COUVERTURE_ERREUR = 0.92, 0.85  # annonces avec texte qui ont des items : 95 % en temps normal
METIERS_ALERTE = 0.95  # offres dont le métier est rattaché à une fiche ROME

RECENT_JOURS, HISTORIQUE_JOURS = 182, 730
MIN_ANNONCES_EMPLOYEUR = 10  # dans chacune des deux périodes, pour la comparaison à employeurs constants
MIN_EMPLOYEURS = 5  # employeurs citant la compétence sur la période récente
T_MAX = 99.0
MIN_EMPLOYEURS_CONSTANTS = 30  # en dessous, pas de test : l'approximation normale du t serait trop optimiste
DEBUT_NOUVEAUTES = date(2023, 1, 1)  # avant, faute d'historique, presque toutes les formes paraissent nouvelles
SEUIL_FDR = 0.10  # taux de fausses découvertes (Benjamini-Hochberg) pour déclarer une compétence en hausse
HISTORIQUE_VOLUME = 30  # le volume est comparé au plus haut des 30 derniers contrôles (une baisse ne devient pas la norme)

# Services du ministère des Armées (champ « organisme ») : principaux auteurs de textes de compétences jusqu'en 2025.
# Les mots « défense » d'autres administrations (Défenseur des droits, zones de défense, SGDSN...) sont écartés.
DEFENSE = (r"(?i)arm[ée]es?\b|défense|armement|^marine$|DIRISI|\((?:DRM|DSNJ|SRHC|SEO|SIAé|DMAé|DTIE|DGRIS|SIMu)\)|ECPAD|"
           r"service de l'aéronautique|^ministère des armées")
DEFENSE_EXCLUS = r"(?i)défenseur|zone de défense|SGDSN|défense nationale \(AAI\)|service de défense et de sécurité|haut fonctionnaire de défense"


def _n(x: int) -> str:
    """Entier à la française (espace fine insécable entre les milliers)."""
    return f"{x:,}".replace(",", "\u202f")


def _pc(x: float, decimales: int = 1) -> str:
    return f"{100 * x:.{decimales}f}".replace(".", ",") + "\u00a0%"


def _date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _controle(code: str, libelle: str, niveau: str, valeur, detail: str) -> dict:
    return {"code": code, "libelle": libelle, "niveau": niveau, "valeur": valeur, "detail": detail}


def _mois_complets(offres: pl.DataFrame) -> list[date]:
    """Mois entièrement couverts par le fichier, du plus ancien au plus récent (même règle que le tableau de bord)."""
    fin = offres["date_publication"].max()
    dernier = fin.replace(day=1) if fin.day >= 25 else (fin.replace(day=1) - timedelta(days=1)).replace(day=1)
    return [m for m in offres.select(pl.col("date_publication").dt.truncate("1mo").unique().sort()).to_series().to_list()
            if web.DEBUT <= m <= dernier]


def _par_mois(offres: pl.DataFrame) -> pl.DataFrame:
    return (
        offres.filter(pl.col("date_publication") >= web.DEBUT)
        .group_by(mois=pl.col("date_publication").dt.truncate("1mo"))
        .agg(
            n=pl.len(),
            texte=pl.col("competences_texte").is_not_null().sum(),
            sans_metier=pl.col("metier").is_null().sum(),
            sans_departement=pl.col("departement").is_null().sum(),
            sans_categorie=pl.col("categorie").is_null().sum(),
        )
        .sort("mois")
    )


def _part(table: pl.DataFrame, colonne: str) -> float:
    return table[colonne].sum() / max(table["n"].sum(), 1)


def plausibles(offres: pl.DataFrame, aujourdhui: date) -> pl.DataFrame:
    """Offres datées au plus de demain : une date aberrante ne doit pas masquer un fichier qui n'est plus mis à jour."""
    return offres.filter(pl.col("date_publication") <= aujourdhui + timedelta(days=1))


def controles_offres(offres: pl.DataFrame, aujourdhui: date, volume_reference: int | None) -> tuple[list[dict], pl.DataFrame]:
    """Contrôles du fichier des offres ; `volume_reference` est le plus haut nombre d'offres des derniers contrôles."""
    resultats = []
    valides = plausibles(offres, aujourdhui)
    fin = valides["date_publication"].max()
    age = (aujourdhui - fin).days
    niveau = ERREUR if age > FRAICHEUR_ERREUR else ALERTE if age > FRAICHEUR_ALERTE else OK
    resultats.append(_controle("fraicheur", "Fraîcheur des offres", niveau, age,
                               f"dernière offre publiée le {_date(fin)}, il y a {age} jours "
                               f"(alerte au-delà de {FRAICHEUR_ALERTE}, erreur au-delà de {FRAICHEUR_ERREUR})"))

    n = offres.height
    if volume_reference:
        niveau = ERREUR if n < BAISSE_VOLUME * volume_reference else OK
        detail = f"{_n(n)} offres, contre {_n(volume_reference)} au plus haut des {HISTORIQUE_VOLUME} derniers contrôles"
    else:
        niveau, detail = OK, f"{_n(n)} offres (premier contrôle)"
    resultats.append(_controle("volume", "Nombre total d'offres", niveau, n, detail))

    doublons = n - offres["reference"].n_unique()
    resultats.append(_controle("doublons", "Références en double", ERREUR if doublons else OK, doublons,
                               "une ligne par référence attendue après consolidation"))

    futures = offres.filter(pl.col("date_publication") > aujourdhui + timedelta(days=1)).height
    resultats.append(_controle("dates_futures", "Dates de publication dans le futur", ALERTE if futures else OK, futures,
                               "offres publiées après demain"))

    connus = set(web.CONNUS)
    inconnus = offres.filter(pl.col("departement").is_not_null() & ~pl.col("departement").is_in(connus)).height
    part = inconnus / n
    resultats.append(_controle("departements", "Départements inconnus", ALERTE if part > 0.01 else OK, round(part, 4),
                               f"{_n(inconnus)} offres avec un code de département hors des 107 connus"))

    mensuel = _par_mois(valides)
    complets = _mois_complets(valides)
    if len(complets) >= 13:
        dernier, un_an = complets[-1], complets[-1].replace(year=complets[-1].year - 1)
        nd = mensuel.filter(pl.col("mois") == dernier)["n"].sum()
        na = mensuel.filter(pl.col("mois") == un_an)["n"].sum()
        # Un mois compté complet dès le 25 : ramené au mois entier pour ne pas paraître en baisse
        jours = ((dernier + timedelta(days=32)).replace(day=1) - dernier).days
        couverts = fin.day if (fin.year, fin.month) == (dernier.year, dernier.month) else jours
        ratio = nd * jours / couverts / max(na, 1)
        niveau = OK if ECART_MOIS[0] <= ratio <= ECART_MOIS[1] else ALERTE
        partiel = f" (données jusqu'au {fin.day}, ramenées au mois entier)" if couverts < jours else ""
        resultats.append(_controle("volume_mensuel", "Offres du dernier mois complet", niveau, round(ratio, 3),
                                   f"{_n(nd)} offres en {dernier:%m/%Y}{partiel} contre {_n(na)} en {un_an:%m/%Y}"))

        recents = mensuel.filter(pl.col("mois").is_in(complets[-3:]))
        reference = mensuel.filter(pl.col("mois").is_in(complets[-15:-3]))
        periodes = f"{complets[-3]:%m/%Y}-{complets[-1]:%m/%Y} contre les douze mois précédents"
        for colonne, libelle in [("sans_metier", "métier"), ("sans_departement", "département"), ("sans_categorie", "catégorie")]:
            r, a = _part(recents, colonne), _part(reference, colonne)
            niveau = ALERTE if r - a > HAUSSE_MANQUANTS else OK
            resultats.append(_controle(f"manquants_{colonne[5:]}", f"Offres sans {libelle}", niveau, round(r, 4),
                                       f"{_pc(r)} contre {_pc(a)} ({periodes})"))
        r, a = _part(recents, "texte"), _part(reference, "texte")
        niveau = ALERTE if r < BAISSE_TEXTES * a else OK
        resultats.append(_controle("textes", "Offres avec un texte de compétences", niveau, round(r, 4),
                                   f"{_pc(r)} contre {_pc(a)} ({periodes})"))
        resultats.append(_contributeurs(valides, complets[-3:], complets[-15:-3], periodes))
    return resultats, mensuel


def _contributeurs(offres: pl.DataFrame, recents: list[date], reference: list[date], periodes: str) -> dict:
    """Gros auteurs de textes de compétences qui publient toujours des offres mais n'écrivent presque plus de textes.

    Les compétences citées reposent sur peu d'employeurs : quand l'un d'eux change sa façon de remplir le formulaire,
    les statistiques bougent sans que la demande ait changé (c'est arrivé fin 2025 avec les services des armées).
    """
    mois = pl.col("date_publication").dt.truncate("1mo")
    x = (
        offres.with_columns(periode=pl.when(mois.is_in(recents)).then(pl.lit("r")).when(mois.is_in(reference)).then(pl.lit("a")))
        .drop_nulls("periode")
        .group_by("organisme")
        .agg(**{f"{c}_{p}": (pl.col("periode") == p).sum() if c == "n" else
                ((pl.col("periode") == p) & pl.col("competences_texte").is_not_null()).sum()
                for c in ("n", "t") for p in ("r", "a")})
    )
    total = max(x["t_a"].sum(), 1)
    ratio = (pl.col("t_r") / len(recents)) / (pl.col("t_a") / len(reference))
    garde = (pl.col("n_r") / len(recents)) / (pl.col("n_a") / len(reference))
    taris = x.filter((pl.col("t_a") >= PART_CONTRIBUTEUR * total) & (ratio < TARISSEMENT) & (garde >= 0.5)).sort("t_a", descending=True)
    part = taris["t_a"].sum() / total
    noms = ", ".join(taris["organisme"].head(4).to_list()) + (" …" if taris.height > 4 else "")
    detail = (f"{taris.height} employeurs qui écrivaient {_pc(part, 0)} des textes n'en écrivent presque plus, tout en publiant "
              f"toujours des offres : {noms} ({periodes})" if taris.height else
              f"aucun gros auteur de textes n'a cessé d'en écrire ({periodes})")
    return _controle("contributeurs", "Auteurs de textes de compétences", ALERTE if taris.height else OK, round(part, 4), detail)


def controles_competences(offres: pl.DataFrame, items: pl.DataFrame, formes: pl.DataFrame, metiers_rome: pl.DataFrame,
                          catalogue_codes: set[str], version: str) -> list[dict]:
    resultats = []
    avec_texte = offres.filter(pl.col("competences_texte").is_not_null())["annonce_id"].unique()
    traitees = items["annonce_id"].unique()
    couverture = avec_texte.is_in(traitees.implode()).mean() if len(avec_texte) else 1.0
    niveau = ERREUR if couverture < COUVERTURE_ERREUR else ALERTE if couverture < COUVERTURE_ALERTE else OK
    resultats.append(_controle("couverture", "Textes de compétences traités", niveau, round(couverture, 4),
                               f"{_pc(couverture)} des {_n(len(avec_texte))} annonces avec un texte ont des items "
                               "(un texte sans liste repérable n'en donne aucun)"))

    vues = items.select("forme").unique().join(formes.select("forme", "code_ogr"), on="forme", how="left")
    sans = vues["code_ogr"].is_null().sum()
    resultats.append(_controle("formes", "Formes sans rattachement", ERREUR if sans else OK, int(sans),
                               f"sur {_n(vues.height)} formes distinctes"))

    hors = formes.filter(pl.col("code_ogr").is_not_null() & ~pl.col("code_ogr").is_in(catalogue_codes)).height
    resultats.append(_controle("catalogue", "Rattachements hors du ROME", ERREUR if hors else OK, hors,
                               "codes absents du catalogue ROME courant"))

    versions = sorted(formes["version"].unique().to_list())
    niveau = OK if versions == [version] else ALERTE
    resultats.append(_controle("version", "Version des rattachements", niveau, ", ".join(versions),
                               f"attendue : {version} (une autre version signale un catalogue ROME qui a changé)"))

    depuis = offres.filter(pl.col("date_publication") >= web.DEBUT)
    part = depuis["metier"].is_in(metiers_rome["metier"].implode()).mean()
    resultats.append(_controle("metiers", "Offres dont le métier a une fiche ROME", ALERTE if part < METIERS_ALERTE else OK,
                               round(part, 4), f"{_pc(part)} des offres depuis 2022"))
    return resultats


def _benjamini_hochberg(p: list[float]) -> list[float]:
    ordre = sorted(range(len(p)), key=lambda i: p[i])
    q = [0.0] * len(p)
    courant = 1.0
    for rang in range(len(p), 0, -1):
        i = ordre[rang - 1]
        courant = min(courant, p[i] * len(p) / rang)
        q[i] = courant
    return q


def _p_bilateral(t: float) -> float:
    return math.erfc(abs(t) / math.sqrt(2))


def derive(offres: pl.DataFrame, items: pl.DataFrame, formes: pl.DataFrame, libelles: dict[str, str], top: int = 15) -> dict:
    """Compétences ROME dont la part dans les annonces a le plus changé : six derniers mois contre deux ans avant.

    - en brut : part des annonces avec texte qui citent la compétence, et part de l'employeur le plus présent parmi
      les annonces récentes qui la citent (un seul employeur à 80 % = un modèle d'annonce, pas une tendance) ;
    - à employeurs constants : pour chaque employeur présent dans les deux périodes, écart de la part de ses annonces
      qui citent la compétence ; moyenne des écarts, test t sur les employeurs (approximation normale, d'où au moins
      30 employeurs), puis correction de Benjamini-Hochberg pour les centaines de compétences testées à la fois.
    """
    annonces = (
        offres.filter(pl.col("competences_texte").is_not_null())
        .group_by("annonce_id").agg(pl.col("date_publication").min(), pl.col("organisme").first())
    )
    fin = annonces["date_publication"].max()
    coupure, debut = fin - timedelta(days=RECENT_JOURS), fin - timedelta(days=RECENT_JOURS + HISTORIQUE_JOURS)
    annonces = annonces.filter(pl.col("date_publication") > debut).with_columns(recent=pl.col("date_publication") > coupure)
    n_recent = annonces["recent"].sum()
    n_avant = annonces.height - n_recent
    citations = (
        items.join(annonces, on="annonce_id").join(formes.select("forme", "code_ogr"), on="forme")
        .drop_nulls("code_ogr").unique(["annonce_id", "code_ogr"])
    )

    brut = (
        citations.group_by("code_ogr")
        .agg(r=pl.col("recent").sum(), a=(~pl.col("recent")).sum(),
             employeurs=pl.col("organisme").filter(pl.col("recent")).n_unique(),
             premier=pl.col("organisme").filter(pl.col("recent")).value_counts(sort=True).first().struct.field("count"))
        .with_columns(pr=pl.col("r") / max(n_recent, 1), pa=pl.col("a") / max(n_avant, 1))
        .with_columns(concentration=pl.col("premier") / pl.col("r"))
    )

    taille = annonces.group_by("organisme").agg(nr=pl.col("recent").sum(), na=(~pl.col("recent")).sum())
    constants = taille.filter((pl.col("nr") >= MIN_ANNONCES_EMPLOYEUR) & (pl.col("na") >= MIN_ANNONCES_EMPLOYEUR))
    k = constants.height
    ecarts = (
        citations.join(constants, on="organisme")
        .group_by("code_ogr", "organisme")
        .agg(cr=pl.col("recent").sum(), ca=(~pl.col("recent")).sum(), nr=pl.col("nr").first(), na=pl.col("na").first())
        .with_columns(d=pl.col("cr") / pl.col("nr") - pl.col("ca") / pl.col("na"))
        .group_by("code_ogr")
        .agg(s=pl.col("d").sum(), s2=(pl.col("d") ** 2).sum())
    )
    lignes = brut.join(ecarts, on="code_ogr", how="left").fill_null(0)
    if k >= MIN_EMPLOYEURS_CONSTANTS:
        # Les employeurs qui ne citent jamais la compétence comptent pour un écart nul
        lignes = lignes.with_columns(m=pl.col("s") / k).with_columns(
            sd=((pl.col("s2") - k * pl.col("m") ** 2) / (k - 1)).clip(lower_bound=0).sqrt())
        lignes = lignes.with_columns(ic=1.96 * pl.col("sd") / math.sqrt(k))
        lignes = lignes.with_columns(
            # Écart identique chez tous les employeurs : certain s'il est non nul (t borné pour rester du JSON valide)
            t=pl.when(pl.col("sd") > 0).then(pl.col("m") / (pl.col("sd") / math.sqrt(k)))
            .otherwise(pl.col("m").sign() * T_MAX).clip(-T_MAX, T_MAX))
        testables = lignes.filter(pl.col("employeurs") >= MIN_EMPLOYEURS)
        q = _benjamini_hochberg([_p_bilateral(t) for t in testables["t"].to_list()])
        lignes = lignes.join(testables.select("code_ogr").with_columns(q=pl.Series(q, dtype=pl.Float64)), on="code_ogr", how="left")
    else:
        lignes = lignes.with_columns(m=pl.lit(0.0), t=pl.lit(0.0), ic=pl.lit(None, dtype=pl.Float64),
                                     q=pl.lit(None, dtype=pl.Float64))

    def ligne(r: dict) -> dict:
        return {"code_ogr": r["code_ogr"], "libelle": libelles.get(r["code_ogr"], r["code_ogr"]), "recent": r["r"], "avant": r["a"],
                "part_recente": round(r["pr"], 5), "part_avant": round(r["pa"], 5), "employeurs": r["employeurs"],
                "concentration": round(r["concentration"], 3) if r["r"] else None,
                "ecart_constant": round(r["m"], 5), "ic": None if r["ic"] is None else round(r["ic"], 5),
                "t": round(r["t"], 2), "q": None if r["q"] is None else round(r["q"], 4)}

    # Classement brut : test de deux proportions (z), qui ne fait pas remonter les compétences citées deux fois
    p = (pl.col("r") + pl.col("a")) / (n_recent + n_avant)
    brutes = lignes.filter(pl.col("employeurs") >= MIN_EMPLOYEURS).with_columns(
        z=(pl.col("pr") - pl.col("pa")) / (p * (1 - p) * (1 / max(n_recent, 1) + 1 / max(n_avant, 1))).sqrt())
    # Test bilatéral, mais seules les hausses sont annoncées comme compétences émergentes
    significatives = lignes.filter(pl.col("q").is_not_null() & (pl.col("q") < SEUIL_FDR) & (pl.col("t") > 0))
    return {
        "periode_recente": [(coupure + timedelta(days=1)).isoformat(), fin.isoformat()],
        "periode_avant": [(debut + timedelta(days=1)).isoformat(), coupure.isoformat()],
        "annonces": {"recente": int(n_recent), "avant": int(n_avant)},
        "employeurs_constants": {"nombre": k, "annonces_recente": int(constants["nr"].sum()), "annonces_avant": int(constants["na"].sum())},
        "competences_testees": int(lignes["q"].is_not_null().sum()),
        "seuil_fdr": SEUIL_FDR,
        "hausses_brutes": [ligne(r) for r in brutes.sort("z", descending=True).head(top).iter_rows(named=True)],
        "baisses_brutes": [ligne(r) for r in brutes.sort("z").head(top).iter_rows(named=True)],
        "hausses_constantes": [ligne(r) for r in lignes.filter(pl.col("employeurs") >= MIN_EMPLOYEURS)
                               .sort("t", descending=True).head(top).iter_rows(named=True)],
        "significatives": [ligne(r) for r in significatives.sort("t", descending=True).iter_rows(named=True)],
        "employeurs_principaux": _poids_employeurs(annonces),
    }


def _poids_employeurs(annonces: pl.DataFrame, n: int = 5) -> list[dict]:
    """Part des annonces avec texte des plus gros employeurs, dans chaque période : ce qui fait bouger les chiffres bruts."""
    nr, na = max(annonces["recent"].sum(), 1), max((~annonces["recent"]).sum(), 1)
    parts = (
        annonces.group_by("organisme").agg(r=pl.col("recent").sum(), a=(~pl.col("recent")).sum())
        .with_columns(pr=pl.col("r") / nr, pa=pl.col("a") / na)
        .with_columns(poids=pl.max_horizontal("pr", "pa"))
        .sort("poids", descending=True).head(n)
    )
    return [{"organisme": r["organisme"], "part_recente": round(r["pr"], 4), "part_avant": round(r["pa"], 4)}
            for r in parts.iter_rows(named=True)]


def nouveautes_par_mois(offres: pl.DataFrame, items: pl.DataFrame) -> list[list]:
    """Pour chaque mois complet : part des items dont la forme n'avait jamais été vue auparavant.

    Les mois de 2022 servent d'historique. Un vocabulaire qui se renouvelle plus vite dégrade le rattachement (les formes nouvelles sont souvent rares, et le
    rattachement des formes rares est le moins fiable, voir le notebook 02).
    """
    dates = offres.filter(pl.col("competences_texte").is_not_null()).group_by("annonce_id").agg(pl.col("date_publication").min())
    x = items.join(dates, on="annonce_id").with_columns(mois=pl.col("date_publication").dt.truncate("1mo"))
    premiere = x.group_by("forme").agg(premier=pl.col("mois").min())
    complets = set(_mois_complets(offres))
    mensuel = (
        x.join(premiere, on="forme").filter(pl.col("mois").is_in(complets) & (pl.col("mois") >= DEBUT_NOUVEAUTES))
        .group_by("mois").agg(items=pl.len(), nouveaux=(pl.col("premier") == pl.col("mois")).sum())
        .sort("mois")
    )
    return [[f"{r['mois']:%Y-%m}", r["items"], r["nouveaux"]] for r in mensuel.iter_rows(named=True)]


def textes_defense(offres: pl.DataFrame) -> list[list]:
    """Pour chaque mois complet : textes de compétences, dont ceux des services des armées, et offres de ces services."""
    defense = pl.col("organisme").str.contains(DEFENSE) & ~pl.col("organisme").str.contains(DEFENSE_EXCLUS)
    texte = pl.col("competences_texte").is_not_null()
    complets = set(_mois_complets(offres))
    mensuel = (
        offres.with_columns(d=defense.fill_null(False), mois=pl.col("date_publication").dt.truncate("1mo"))
        .filter(pl.col("mois").is_in(complets))
        .group_by("mois").agg(textes=texte.sum(), textes_defense=(texte & pl.col("d")).sum(), offres_defense=pl.col("d").sum())
        .sort("mois")
    )
    return [[f"{r['mois']:%Y-%m}", r["textes"], r["textes_defense"], r["offres_defense"]] for r in mensuel.iter_rows(named=True)]


def statut(controles: list[dict]) -> str:
    return max((c["niveau"] for c in controles), key=GRAVITE.get, default=OK)


def volume_reference(ancien: list[dict]) -> int | None:
    return max((h.get("offres") or 0 for h in ancien[-HISTORIQUE_VOLUME:]), default=0) or None


def rapport(offres: pl.DataFrame, items: pl.DataFrame, formes: pl.DataFrame, metiers_rome: pl.DataFrame,
            catalogue: pl.DataFrame, version: str, aujourdhui: date, ancien: list[dict],
            source: dict | None = None) -> dict:
    ctrl_offres, mensuel = controles_offres(offres, aujourdhui, volume_reference(ancien))
    ctrl_comp = controles_competences(offres, items, formes, metiers_rome, set(catalogue["code_ogr"].to_list()), version)
    controles = ctrl_offres + ctrl_comp
    libelles = dict(zip(catalogue["code_ogr"].to_list(), catalogue["libelle"].to_list()))
    valides = plausibles(offres, aujourdhui)
    return {
        "date": aujourdhui.isoformat(),
        "statut": statut(controles),
        "offres": offres.height,
        "derniere_publication": valides["date_publication"].max().isoformat(),
        "source": source or {},
        "controles": controles,
        "mensuel": [[f"{r['mois']:%Y-%m}", r["n"], r["texte"]] for r in mensuel.iter_rows(named=True)],
        "mois_complets": [f"{m:%Y-%m}" for m in _mois_complets(valides)],
        "textes_defense": textes_defense(valides),
        "nouveautes": nouveautes_par_mois(valides, items),
        "derive": derive(valides, items, formes, libelles),
    }


def resume(r: dict) -> dict:
    """Ligne de l'historique des contrôles."""
    return {"date": r["date"], "statut": r["statut"], "offres": r["offres"], "derniere_publication": r["derniere_publication"],
            "alertes": [c["code"] for c in r["controles"] if c["niveau"] != OK]}


def historique(ancien: list[dict], r: dict, garder: int = 400) -> list[dict]:
    """Ajoute le résumé du jour (un seul par date : le dernier passage de la journée remplace les précédents)."""
    return ([h for h in ancien if h["date"] != r["date"]] + [resume(r)])[-garder:]
