"""Ligne de commande : `offres collecte --mode jour|stock`, `offres referentiels`, `offres rome`, `offres csp`, `offres competences`,
`offres site`, `offres suivi`."""

from __future__ import annotations

import argparse
import json
import time
from datetime import timedelta
from pathlib import Path

import polars as pl

from offres import collecte, csp, rome, sonde
from offres.api import PLAFOND, Client, ErreurApi

TAILLE_LOT = 50_000  # offres gardées en mémoire avant écriture d'un morceau


def collecter(dossier: Path, mode: str, jours: int, annees: int) -> None:
    client = Client()
    try:
        client.jeton()
    except ErreurApi as e:
        if "invalid_scope" not in str(e):
            raise
        # L'API Offres d'emploi est en accès restreint : tant que l'application n'y est pas abonnée, on le signale
        # sans faire échouer la collecte quotidienne
        print("::warning title=Collecte::Application non abonnée à l'API Offres d'emploi v2 (accès restreint) : collecte ignorée.")
        return
    vue_le = collecte.maintenant()
    jour = vue_le.date().isoformat()
    debut = vue_le - (timedelta(days=jours) if mode == "jour" else timedelta(days=365 * annees))
    morceaux = dossier / "tmp" / f"{jour}_{mode}"
    for ancien_morceau in morceaux.glob("*.parquet") if morceaux.exists() else []:
        ancien_morceau.unlink()  # restes d'un passage interrompu le même jour
    morceaux.mkdir(parents=True, exist_ok=True)
    tranches: list[dict] = []
    lot: list[dict] = []
    depart = time.monotonic()

    def vider() -> None:
        if lot:
            collecte.en_table(lot, vue_le).write_parquet(morceaux / f"part-{len(list(morceaux.glob('*.parquet'))):04d}.parquet")
            lot.clear()

    for n, offre in enumerate(collecte.offres_periode(client, debut, vue_le, journal=tranches), start=1):
        lot.append(offre)
        if len(lot) >= TAILLE_LOT:
            vider()
            print(f"  {n} offres, {client.appels} appels, {time.monotonic() - depart:.0f} s")
    vider()

    cible = dossier / "offres"
    cible.mkdir(parents=True, exist_ok=True)
    fichier = cible / f"offres_{jour}_{mode}.parquet"
    parts = sorted(morceaux.glob("*.parquet"))
    if not parts:
        raise SystemExit("Aucune offre reçue : vérifier les identifiants et les critères")
    # Les doublons entre morceaux (offre actualisée pendant la collecte) sont retirés ici, en flux
    pl.scan_parquet(parts).unique("id", keep="last").sink_parquet(fichier, compression="zstd")
    for p in parts:
        p.unlink()
    morceaux.rmdir()

    offres = pl.scan_parquet(fichier).select("id", "date_creation", "date_actualisation").collect()
    journal = pl.DataFrame(tranches, schema={"debut": pl.Datetime("us", "UTC"), "fin": pl.Datetime("us", "UTC"), "criteres": pl.Utf8,
                                             "total": pl.Int64, "tronque": pl.Boolean, "manquantes": pl.Int64})
    chemin_index = dossier / "index.parquet"
    ancien = pl.read_parquet(chemin_index) if chemin_index.exists() else None
    # Une photo du stock ne sert à dater les disparitions que si aucune offre n'a été perdue en route
    perdues = journal.height > 0 and (journal["tronque"].any() or journal["manquantes"].sum() > 0)
    if mode == "stock" and perdues:
        print("::warning title=Collecte::Offres perdues (plafond ou types de contrat) : disparitions non datées cette fois.")
    index = collecte.mettre_a_jour_index(ancien, offres, vue_le, complet=(mode == "stock" and not perdues))
    index.write_parquet(chemin_index)

    rapport = {
        "date": vue_le.isoformat(),
        "mode": mode,
        "periode": [debut.isoformat(), vue_le.isoformat()],
        "offres": offres.height,
        "nouvelles": index.filter(pl.col("premiere_vue") == vue_le).height,
        "index": index.height,
        "en_ligne": index.filter("en_ligne").height,
        "tranches": journal.height,
        "tranches_tronquees": int(journal["tronque"].sum()) if journal.height else 0,
        "offres_hors_types_contrat": int(journal["manquantes"].sum()) if journal.height else 0,
        "offres_perdues_plafond": int(journal.filter("tronque")["total"].sum() - PLAFOND * journal["tronque"].sum())
        if journal.height
        else 0,
        "appels": client.appels,
        "duree_s": round(time.monotonic() - depart),
    }
    (dossier / "rapports").mkdir(exist_ok=True)
    (dossier / "rapports" / f"collecte_{jour}_{mode}.json").write_text(json.dumps(rapport, ensure_ascii=False, indent=1))
    print(json.dumps(rapport, ensure_ascii=False, indent=1))
    print(f"-> {fichier} ({fichier.stat().st_size / 1e6:.1f} Mo), index {chemin_index}")


REFERENTIELS = [
    "appellations", "metiers", "domaines", "departements", "regions", "secteursActivites", "typesContrats",
    "naturesContrats", "niveauxFormations", "themes", "communes",
]


def collecter_referentiels(dossier: Path) -> None:
    client = Client()
    cible = dossier / "referentiels"
    cible.mkdir(parents=True, exist_ok=True)
    for nom in REFERENTIELS:
        valeurs = client.referentiel(nom)
        (cible / f"{nom}.json").write_text(json.dumps(valeurs, ensure_ascii=False))
        print(f"{nom} : {len(valeurs)} entrées")


def extraire_competences(dossier: Path, cache: Path | None) -> None:
    from offres import competences, donnees
    from offres.embeddings import Modele

    cible = dossier / "competences"
    cible.mkdir(parents=True, exist_ok=True)
    depart = time.monotonic()
    offres = donnees.offres_service_public()
    items = competences.items_des_offres(offres)
    modele = Modele("e5")
    precedent = pl.read_parquet(cache) if cache and cache.exists() else None
    formes = competences.rattacher_formes(items, modele, precedent)
    formes.write_parquet(cible / "competences_formes.parquet")
    items.select("annonce_id", "forme").write_parquet(cible / "competences_items.parquet")
    metiers = competences.rattacher_metiers(offres, modele)
    metiers.write_parquet(cible / "metiers_rome.parquet")
    rapport = {
        "version": competences.VERSION,
        "offres_avec_texte": items["annonce_id"].n_unique(),
        "items": items.height,
        "formes": formes.height,
        "metiers": metiers.height,
        "duree_s": round(time.monotonic() - depart),
    }
    (cible / "competences_rapport.json").write_text(json.dumps(rapport, ensure_ascii=False, indent=1))
    print(json.dumps(rapport, ensure_ascii=False, indent=1))


def suivre(sortie: Path, ancien_historique: Path | None) -> str:
    """Contrôles et dérive : écrit suivi_dernier.json et suivi_historique.json, renvoie le statut (ok, alerte, erreur)."""
    from offres import competences, donnees, suivi

    offres = donnees.offres_service_public()
    items = pl.read_parquet(donnees.chemin("competences_items.parquet"))
    formes = pl.read_parquet(donnees.chemin("competences_formes.parquet"))
    metiers_rome = pl.read_parquet(donnees.chemin("metiers_rome.parquet"))
    catalogue = competences.catalogue_rome()
    ancien = json.loads(ancien_historique.read_text()) if ancien_historique and ancien_historique.exists() else []
    # Le nom de chaque fichier annuel commence par sa date de mise à jour sur data.gouv.fr (AAAAMMJJ)
    maj = max(offres["fichier_source"].unique().to_list())[:8]
    source = {"mise_a_jour_fichier": f"{maj[:4]}-{maj[4:6]}-{maj[6:]}" if maj.isdigit() else None}
    rapport = suivi.rapport(offres, items, formes, metiers_rome, catalogue, competences.version(catalogue),
                            collecte.maintenant().date(), ancien[-1] if ancien else None, source)
    sortie.mkdir(parents=True, exist_ok=True)
    (sortie / "suivi_dernier.json").write_text(json.dumps(rapport, ensure_ascii=False, indent=1))
    (sortie / "suivi_historique.json").write_text(json.dumps(suivi.historique(ancien, rapport), ensure_ascii=False, indent=1))
    for c in rapport["controles"]:
        print(f"{c['niveau']:>7}  {c['libelle']} : {c['detail']}")
        if c["niveau"] != suivi.OK:
            print(f"::{'error' if c['niveau'] == suivi.ERREUR else 'warning'} title={c['libelle']}::{c['detail']}")
    return rapport["statut"]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="offres", description=__doc__)
    parser.add_argument("--dossier", type=Path, default=Path("donnees"), help="dossier des données")
    sous = parser.add_subparsers(dest="commande", required=True)
    c = sous.add_parser("collecte", help="collecter les offres de France Travail")
    c.add_argument("--mode", choices=["jour", "stock"], default="jour",
                   help="jour : offres créées ces derniers jours ; stock : toutes les offres en ligne")
    c.add_argument("--jours", type=int, default=3, help="profondeur du mode jour")
    c.add_argument("--annees", type=int, default=3, help="profondeur du mode stock")
    sous.add_parser("referentiels", help="référentiels de l'API (métiers, appellations, départements...)")
    c2 = sous.add_parser("csp", help="offres de Choisir le service public (open data, sans identifiants)")
    c2.add_argument("--rapport-precedent", type=Path, help="rapport du passage précédent, pour refuser une régression")
    sous.add_parser("sonde", help="diagnostic : portées OAuth et routes accessibles avec les identifiants")
    sous.add_parser("rome", help="référentiel ROME 4.0 (open data) : compétences et savoirs par métier")
    c3 = sous.add_parser("competences", help="compétences des offres rattachées au ROME, métiers rattachés aux fiches ROME")
    c4 = sous.add_parser("reclasser", help="reclassement des propositions par un LLM local (Ollama)")
    c4.add_argument("--modele", default="qwen2.5:7b", help="modèle Ollama déjà téléchargé")
    c4.add_argument("--entree", type=Path, required=True, help="JSON des items et de leurs candidats")
    c4.add_argument("--sortie", type=Path, required=True, help="JSON des choix (reprise possible)")
    c4.add_argument("--lot", type=int, default=8, help="items par requête")
    c5 = sous.add_parser("site", help="site statique : article, tableau de bord et outil, avec leurs données")
    c5.add_argument("--sortie", type=Path, default=Path("_site"), help="dossier du site construit")
    c6 = sous.add_parser("suivi", help="contrôles des données publiées et dérive des compétences")
    c6.add_argument("--sortie", type=Path, default=Path("suivi"), help="dossier des rapports de suivi")
    c6.add_argument("--historique", type=Path, help="suivi_historique.json du passage précédent")
    c3.add_argument("--cache", type=Path, help="competences_formes.parquet du passage précédent (formes déjà rattachées)")
    args = parser.parse_args(argv)

    if args.commande == "collecte":
        collecter(args.dossier, args.mode, args.jours, args.annees)
    elif args.commande == "referentiels":
        collecter_referentiels(args.dossier)
    elif args.commande == "csp":
        csp.telecharger(args.dossier / "csp", args.rapport_precedent)
    elif args.commande == "sonde":
        sonde.sonder()
    elif args.commande == "rome":
        rome.telecharger(args.dossier / "rome")
    elif args.commande == "reclasser":
        from offres import reclassement

        reclassement.reclasser(args.entree, args.sortie, args.modele, args.lot)
    elif args.commande == "competences":
        extraire_competences(args.dossier, args.cache)
    elif args.commande == "site":
        from offres import web

        print(json.dumps(web.construire(args.sortie), ensure_ascii=False, indent=1))
    elif args.commande == "suivi" and suivre(args.sortie, args.historique) == "erreur":
        raise SystemExit("Au moins un contrôle en erreur")


if __name__ == "__main__":
    main()
