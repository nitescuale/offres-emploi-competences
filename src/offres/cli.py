"""Ligne de commande : `offres collecte --mode jour|stock`, `offres referentiels`, `offres rome`."""

from __future__ import annotations

import argparse
import json
import time
from datetime import timedelta
from pathlib import Path

import polars as pl

from offres import collecte, csp, rome, sonde
from offres.api import Client

TAILLE_LOT = 50_000  # offres gardées en mémoire avant écriture d'un morceau


def collecter(dossier: Path, mode: str, jours: int, annees: int) -> None:
    client = Client()
    vue_le = collecte.maintenant()
    jour = vue_le.date().isoformat()
    debut = vue_le - (timedelta(days=jours) if mode == "jour" else timedelta(days=365 * annees))
    morceaux = dossier / "tmp" / f"{jour}_{mode}"
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
    chemin_index = dossier / "index.parquet"
    ancien = pl.read_parquet(chemin_index) if chemin_index.exists() else None
    index = collecte.mettre_a_jour_index(ancien, offres, vue_le, complet=(mode == "stock"))
    index.write_parquet(chemin_index)

    journal = pl.DataFrame(tranches)
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
        "offres_perdues_plafond": int(journal.filter("tronque")["total"].sum() - 1150 * journal["tronque"].sum())
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
    sous.add_parser("csp", help="offres de Choisir le service public (open data, sans identifiants)")
    sous.add_parser("sonde", help="diagnostic : portées OAuth et routes accessibles avec les identifiants")
    sous.add_parser("rome", help="référentiel ROME 4.0 (open data) : compétences et savoirs par métier")
    args = parser.parse_args(argv)

    if args.commande == "collecte":
        collecter(args.dossier, args.mode, args.jours, args.annees)
    elif args.commande == "referentiels":
        collecter_referentiels(args.dossier)
    elif args.commande == "csp":
        csp.telecharger(args.dossier / "csp")
    elif args.commande == "sonde":
        sonde.sonder()
    elif args.commande == "rome":
        rome.telecharger(args.dossier / "rome")


if __name__ == "__main__":
    main()
