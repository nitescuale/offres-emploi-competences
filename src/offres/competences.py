"""Extraction des compétences : découpage des textes en items, catalogue ROME 4.0, rapprochement item -> ROME.

Trois méthodes de rapprochement, comparées sur un échantillon annoté (notebook 02) :
- `dictionnaire` : libellé identique après normalisation (casse, accents, tournures « connaissance de », « savoir »...) ;
- `tfidf` : plus proche voisin en n-grammes de caractères, robuste aux fautes et aux variantes de forme ;
- `embeddings` : plus proche voisin dans l'espace d'un modèle de phrases multilingue, qui capte le sens
  (« travail en équipe » ~ « Avoir l'esprit d'équipe »).
"""

from __future__ import annotations

import re
import unicodedata

import numpy as np
import polars as pl

from offres import donnees

# Titres de rubriques fréquents dans les textes, à ne pas prendre pour des compétences (testés sur la forme
# minuscule sans accents ni ponctuation) : « Savoirs théoriques et pratiques », « Compétences opérationnelles »...
_MOT_TITRE = (r"(?:savoirs?|savoir faire|savoir etre|savoirs etre|connaissances?|competences?|qualites?|aptitudes?|profil|"
              r"formations?|experiences?|capacites?|outils|nom|intitule)")
_ADJ_TITRE = (r"(?:requis\w*|attendu\w*|techniques?|operationnel\w*|theoriques?|pratiques?|generaux|generales?|disciplinaires|"
              r"comportement\w*|transvers\w*|professionnel\w*|relationnel\w*|specifiques?|personnel\w*|souhaite\w*|"
              r"recherche\w*|necessaires?|cles|mobilise\w*|associe\w*|manageria\w*|metiers?|indispensables?|du|de|des|la|le|"
              r"les|poste|candidat|et|ou|faire|etre|savoirs?|connaissances?|competences?|qualites?|aptitudes?|niveau)")
_TITRE = re.compile(rf"^(?:les )?{_MOT_TITRE}(?: {_ADJ_TITRE}){{0,6}}$")
# Puces : tirets, symboles (y compris les caractères privés de Wingdings collés depuis Word), numéros
_PUCE = re.compile(r"^\s*(?:[^\w\s(«\"'.]+|o(?=\s)|\d+[.)]|[a-hA-H]\)(?=\s))\s*")
# « Management : expertise » : niveau attendu, à retirer pour garder la compétence
_NIVEAU = re.compile(
    r"^(?:niveau\s+)?(?:expert(?:ise)?|maitrise|pratique|application|notions?|sensibilisation|initie|initiation|confirme|"
    r"debutant|elementaire|intermediaire|avance|requis|souhaite|indispensable|apprecie|\d)\b(?: \w+){0,2}"
)
_RENVOI = re.compile(r"^(?:cf|voir|se referer)\b")


def sans_accents(texte: str) -> str:
    texte = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in texte if not unicodedata.combining(c))


def _forme_brute(texte: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+#]+", " ", sans_accents(texte.lower()))).strip()


_PREFIXE = re.compile(
    r"^(?!ma[iî]trise de soi\b)(?:(?:tr[eè]s )?(?:bonnes?|solides?|excellentes?) )?"
    r"(?:connaissances?|ma[iî]trise|capacit[eé]s?|aptitudes?|savoir|[eê]tre capable|sens|notions?)(?= )"
    r"(?: (?:de la|des|du|de l'|de|d'|à|a|en))? ?"
)
_EXIGENCE = re.compile(r"[\s(]+(?:indispensables?|appr[eé]ci[eé]\w*|souhait[eé]\w*|serait un (?:atout|plus)|un plus|requis\w*|exig[eé]\w*)\)?$")


def nettoyer(texte: str) -> str:
    """Item lisible pour un modèle de langue : minuscules (les textes en capitales gênent les modèles), accents gardés,
    sans les tournures qui n'ajoutent rien (« bonne connaissance de », « capacité à »...) ni les mentions d'exigence."""
    t = re.sub(r"\s+", " ", texte.lower().replace("’", "'")).strip(" .,;:-")
    t = _EXIGENCE.sub("", t)
    reste = _PREFIXE.sub("", t, count=1)
    return reste if len(reste) >= 3 else t


def normaliser(texte: str) -> str:
    """Forme de comparaison : `nettoyer`, puis sans accents ni ponctuation."""
    return _forme_brute(nettoyer(texte))


def segmenter(texte: str | None) -> list[str]:
    """Texte libre -> items de compétence (une ligne, une puce, ou un élément d'une liste à virgules)."""
    if not texte:
        return []
    items: list[str] = []
    for ligne in re.split(r"[\r\n\t]+|;|•|\uf0a7|\uf0b7", texte):
        ligne = _PUCE.sub("", ligne).strip(" .,:\t-")
        # « Savoir-être : rigueur, autonomie » : le titre est suivi des items sur la même ligne
        if ":" in ligne:
            tete, _, reste = ligne.partition(":")
            if _NIVEAU.match(_forme_brute(reste)):
                ligne = tete.strip()
            elif _TITRE.match(_forme_brute(tete)) or _NIVEAU.match(_forme_brute(tete)) or len(tete.split()) <= 3:
                ligne = reste.strip(" .,")
        forme = _forme_brute(ligne)
        if not ligne or _TITRE.match(forme) or _NIVEAU.fullmatch(forme) or _RENVOI.match(forme):
            continue
        morceaux = [m.strip(" .") for m in ligne.split(",")]
        # Une liste de mots courts (« Autonome, Rigoureux, Dynamique ») est éclatée ; une phrase avec virgules ne l'est pas
        if len(morceaux) > 1 and all(0 < len(m.split()) <= 4 for m in morceaux):
            items.extend(m for m in morceaux if m)
        else:
            items.append(ligne)
    return [i for i in items if 3 <= len(i) <= 200]


def catalogue_rome() -> pl.DataFrame:
    """Savoir-faire, savoir-être et savoirs du ROME 4.0, avec leur rattachement (domaine, macro-compétence...)."""
    comp = donnees.rome("referentiel_competence").select(
        pl.col("code_ogr"), pl.col("libelle_competence").alias("libelle"), pl.col("cat_comp").alias("type"),
        pl.col("sous_cat_comp").alias("sous_type"),
    )
    arbre = donnees.rome("arborescence_competences").select(
        pl.col("code_ogr_competence").alias("code_ogr"), "domaine_competence", "enjeu", "libelle_macro_competence",
    ).unique("code_ogr")
    savoirs = donnees.rome("referentiel_savoir").select(
        pl.col("code_ogr_savoir").alias("code_ogr"), pl.col("libelle_savoir").alias("libelle"), pl.lit("Savoir").alias("type"),
        pl.col("categorie_savoir").alias("sous_type"),
    )
    return (
        pl.concat([comp.join(arbre, on="code_ogr", how="left"), savoirs], how="diagonal")
        .with_columns(pl.col("libelle").map_elements(normaliser, return_dtype=pl.Utf8).alias("forme"))
        .unique("code_ogr", keep="first", maintain_order=True)
    )


def sans_double_genre(libelle: str, feminin_dabord: bool) -> str:
    """« Chargée / Chargé de paie » (fonction publique, féminin d'abord) et « Chargé / Chargée de paie » (ROME) -> « Chargé
    de paie » : la double forme brouille la comparaison des libellés."""
    if " / " not in libelle:
        return libelle
    a, b = libelle.split(" / ", 1)
    if feminin_dabord:
        return b
    return " ".join([a, *b.split()[len(a.split()):]])


def catalogue_appellations() -> pl.DataFrame:
    """Les 14 000 appellations du ROME (« Data scientist », « Gestionnaire paie »...) avec leur fiche métier : sert à
    rattacher chaque métier de la fonction publique à un code ROME, donc aux compétences de sa fiche."""
    fiches = donnees.rome("referentiel_code_rome").select("code_rome", "libelle_rome")
    return (
        donnees.rome("referentiel_appellation")
        .filter(pl.col("peu_usite") != "O")
        .select("code_ogr", pl.col("libelle_appellation_long").alias("libelle"), "code_rome")
        .join(fiches, on="code_rome", how="left")
        .with_columns(pl.col("libelle").map_elements(lambda x: sans_double_genre(x, False).lower(), return_dtype=pl.Utf8)
                      .alias("texte"))
        .with_columns(pl.col("texte").map_elements(normaliser, return_dtype=pl.Utf8).alias("forme"))
    )


def competences_par_fiche() -> pl.DataFrame:
    """Compétences et savoirs attachés à chaque fiche ROME (`coeur_metier` = Principale pour le cœur du métier)."""
    return donnees.rome("coherence_item").with_columns(pl.col("coeur_metier").fill_null("").eq("Principale").alias("coeur"))


def _centrer(scores: np.ndarray) -> np.ndarray:
    """Scores centrés-réduits par ligne : rend comparables des similarités d'échelles différentes (TF-IDF ~0-1,
    e5 ~0,75-0,95) avant de les additionner."""
    return (scores - scores.mean(1, keepdims=True)) / (scores.std(1, keepdims=True) + 1e-9)


class Rapprocheur:
    """Rapproche des items (ou des intitulés de métier) d'un catalogue ROME ; renvoie code, libellé et score de la
    meilleure entrée.

    Méthodes : `dictionnaire` (forme identique), `tfidf` (n-grammes de caractères), `embeddings` (modèle de phrases,
    usage symétrique : « query: » des deux côtés pour e5), `hybride` (somme des scores TF-IDF et embeddings centrés-
    réduits, la meilleure sur l'échantillon annoté du notebook 02). Le catalogue a une colonne `forme` (voir
    `normaliser`) et, pour les embeddings, une colonne `texte` (à défaut, `libelle`).
    """

    def __init__(self, catalogue: pl.DataFrame, methode: str = "hybride", modele=None):
        self.catalogue = catalogue
        self.methode = methode
        self.formes = catalogue["forme"].to_list()
        if methode not in ("dictionnaire", "tfidf", "embeddings", "hybride"):
            raise ValueError(methode)
        if methode == "dictionnaire":
            index: dict[str, int] = {}
            for i, f in enumerate(self.formes):
                index.setdefault(f, i)
            self.index = index
        if methode in ("tfidf", "hybride"):
            from sklearn.feature_extraction.text import TfidfVectorizer

            self.vect = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, dtype=np.float32)
            self.matrice = self.vect.fit_transform(self.formes)
        if methode in ("embeddings", "hybride"):
            if modele is None:
                raise ValueError(f"méthode {methode} : fournir un modèle (voir offres.embeddings)")
            self.modele = modele
            textes = catalogue["texte"] if "texte" in catalogue.columns else catalogue["libelle"]
            self.vecteurs = modele.encoder(textes.to_list(), requete=True)

    def scores(self, items: list[str]) -> np.ndarray:
        """Matrice items x catalogue des scores de la méthode (sauf dictionnaire)."""
        if self.methode == "tfidf":
            return (self.vect.transform([normaliser(i) for i in items]) @ self.matrice.T).toarray()
        emb = self.modele.encoder([nettoyer(i) for i in items], requete=True) @ self.vecteurs.T
        if self.methode == "embeddings":
            return emb
        tfidf = (self.vect.transform([normaliser(i) for i in items]) @ self.matrice.T).toarray()
        return _centrer(emb) + _centrer(tfidf)

    def candidats(self, items: list[str], k: int = 5, lot: int = 1000) -> list[list[tuple[int, float]]]:
        """Pour chaque item, les k meilleures entrées du catalogue (indice, score), calculées par lots pour tenir en mémoire."""
        if self.methode == "dictionnaire":
            return [[(self.index[f], 1.0)] if (f := normaliser(i)) in self.index else [] for i in items]
        resultat: list[list[tuple[int, float]]] = []
        for debut in range(0, len(items), lot):
            scores = self.scores(items[debut : debut + lot])
            k_ = min(k, scores.shape[1])
            meilleurs = np.argpartition(-scores, k_ - 1, axis=1)[:, :k_]
            valeurs = np.take_along_axis(scores, meilleurs, axis=1)
            ordre = np.argsort(-valeurs, axis=1)
            meilleurs, valeurs = np.take_along_axis(meilleurs, ordre, 1), np.take_along_axis(valeurs, ordre, 1)
            resultat.extend([list(zip(m.tolist(), v.tolist())) for m, v in zip(meilleurs, valeurs)])
        return resultat

    def rapprocher(self, items: list[str], seuil: float | None = None) -> pl.DataFrame:
        """Meilleure entrée pour chaque item ; sous le seuil (s'il est donné), pas de rattachement."""
        lignes = []
        codes, libelles = self.catalogue["code_ogr"], self.catalogue["libelle"]
        for item, cands in zip(items, self.candidats(items, k=1)):
            if cands and (seuil is None or cands[0][1] >= seuil):
                j, score = cands[0]
                lignes.append({"item": item, "code_ogr": codes[j], "libelle_rome": libelles[j], "score": score})
            else:
                lignes.append({"item": item, "code_ogr": None, "libelle_rome": None, "score": cands[0][1] if cands else None})
        return pl.DataFrame(lignes, schema={"item": pl.Utf8, "code_ogr": pl.Utf8, "libelle_rome": pl.Utf8, "score": pl.Float64})


CANDIDATS = 10
VERSION = "hybride-e5-v1"  # change si la méthode ou le catalogue change : les rattachements en cache sont alors refaits


def items_des_offres(offres: pl.DataFrame) -> pl.DataFrame:
    """Une ligne par (annonce, item) pour les offres qui ont un texte de compétences, avec la forme normalisée."""
    return (
        offres.filter(pl.col("competences_texte").is_not_null())
        .unique("annonce_id")
        .select("annonce_id", pl.col("competences_texte").map_elements(segmenter, return_dtype=pl.List(pl.Utf8)).alias("item"))
        .explode("item")
        .drop_nulls("item")
        .with_columns(pl.col("item").map_elements(normaliser, return_dtype=pl.Utf8).alias("forme"))
        .filter(pl.col("forme").str.len_chars() >= 2)
        .unique(["annonce_id", "forme"])
    )


def rattacher_formes(items: pl.DataFrame, modele, cache: pl.DataFrame | None = None) -> pl.DataFrame:
    """Forme -> compétence ROME (méthode hybride). Les formes déjà rattachées avec la même VERSION sont reprises du cache."""
    formes = items.group_by("forme").agg(pl.col("item").first(), pl.len().alias("occurrences"))
    deja = (cache.filter(pl.col("version") == VERSION).select("forme", "code_ogr", "score", "candidats")
            if cache is not None and "candidats" in cache.columns else None)
    a_faire = formes.join(deja, on="forme", how="anti") if deja is not None else formes
    print(f"{formes.height} formes, {a_faire.height} à rattacher")
    schema = {"forme": pl.Utf8, "code_ogr": pl.Utf8, "score": pl.Float64, "candidats": pl.List(pl.Utf8)}
    nouveaux = pl.DataFrame(schema=schema)
    if a_faire.height:
        catalogue = catalogue_rome()
        codes = catalogue["code_ogr"].to_list()
        # Les 10 meilleures propositions sont gardées pour un éventuel reclassement par LLM (offres.reclassement)
        cands = Rapprocheur(catalogue, "hybride", modele).candidats(a_faire["item"].to_list(), k=CANDIDATS)
        nouveaux = pl.DataFrame({
            "forme": a_faire["forme"], "code_ogr": [codes[c[0][0]] for c in cands], "score": [c[0][1] for c in cands],
            "candidats": [[codes[j] for j, _ in c] for c in cands],
        }, schema=schema)
    tout = pl.concat([deja, nouveaux]) if deja is not None else nouveaux
    return formes.select("forme", "occurrences").join(tout, on="forme", how="left").with_columns(version=pl.lit(VERSION))


def rattacher_metiers(offres: pl.DataFrame, modele) -> pl.DataFrame:
    """Métier de la fonction publique -> appellation et fiche ROME (méthode hybride, libellés sans double genre)."""
    metiers = offres.group_by("metier").len().drop_nulls("metier")
    app = catalogue_appellations()
    textes = [sans_double_genre(m, True).lower() for m in metiers["metier"].to_list()]
    r = Rapprocheur(app, "hybride", modele).rapprocher(textes)
    return metiers.rename({"len": "offres"}).with_columns(
        code_ogr_appellation=r["code_ogr"], appellation=r["libelle_rome"], score=r["score"],
    ).join(app.select(pl.col("code_ogr").alias("code_ogr_appellation"), "code_rome", "libelle_rome"),
           on="code_ogr_appellation", how="left")
