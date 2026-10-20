// Extraction des compétences dans le navigateur : la même découpe en items et la même normalisation que le module
// Python `offres.competences`, puis le rapprochement au ROME par TF-IDF (n-grammes de caractères de 3 à 5, comme
// scikit-learn `TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)`).
// Module ES utilisable dans le navigateur et sous Node (tests de parité avec Python : tests/test_site.py).

/** Espaces au sens de Python (`str.split()` sans argument). */
const ESPACES = " \u0009\u000a\u000d\u000b\u000c\u001c\u001d\u001e\u001f\u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000";
const mots = (texte) => texte.split(new RegExp(`[${ESPACES}]+`)).filter(Boolean);
const ESPACES_RE = new RegExp(`[${ESPACES}]+`, "g");

// Lettres et chiffres Unicode : le `\w` de Python, que celui de JavaScript (ASCII) ne couvre pas
const W = "[\\p{L}\\p{N}_]";

const MOT_TITRE = "(?:savoirs?|savoir faire|savoir etre|savoirs etre|connaissances?|competences?|qualites?|aptitudes?|profil|" +
  "formations?|experiences?|capacites?|outils|nom|intitule)";
const ADJ_TITRE = "(?:requis\\w*|attendu\\w*|techniques?|operationnel\\w*|theoriques?|pratiques?|generaux|generales?|disciplinaires|" +
  "comportement\\w*|transvers\\w*|professionnel\\w*|relationnel\\w*|specifiques?|personnel\\w*|souhait\\w*|anterieur\\w*|" +
  "recherche\\w*|necessaires?|cles|mobilise\\w*|associe\\w*|manageria\\w*|metiers?|indispensables?|du|de|des|la|le|" +
  "les|poste|candidat|et|ou|faire|etre|savoirs?|connaissances?|competences?|qualites?|aptitudes?|experiences?|outils?|niveau)";
// Ces trois motifs s'appliquent à la forme brute (ASCII) : `\w` et `\b` y ont le même sens qu'en Python
const TITRE = new RegExp(`^(?:les )?${MOT_TITRE}(?: ${ADJ_TITRE}){0,6}$`);
const NIVEAU = new RegExp(
  "^(?:niveau\\s+)?(?:expert(?:ise)?|maitrise|pratique|application|notions?|sensibilisation|initie|initiation|confirme|" +
  "debutant|elementaire|intermediaire|avance|requis|souhaite|indispensable|apprecie|[abc][12]|\\d)\\b" +
  "(?: (?!(?:de|d|des|du|en|l|la|le|les)\\b)\\w+){0,2}",
);
// `re.fullmatch` de Python : le motif entier doit couvrir la chaîne (un `match` JavaScript peut s'arrêter avant)
const NIVEAU_ENTIER = new RegExp(`^(?:${NIVEAU.source.slice(1)})$`);
const RENVOI = /^(?:cf|voir|se referer)\b/;
// Espaces au sens de Python : le `\s` de JavaScript compte en plus l'indicateur d'ordre des octets (U+FEFF)
const S = `[${ESPACES}]`;
const PUCE = new RegExp(`^${S}*(?:[^\\p{L}\\p{N}_${ESPACES}(«"'.]+|o(?=${S})|\\d+[.)]|[a-hA-H]\\)(?=${S}))${S}*`, "u");
const PREFIXE = new RegExp(
  "^(?!ma[iî]trise de soi\\b)(?:(?:tr[eè]s )?(?:bonnes?|solides?|excellentes?) )?" +
  "(?:(?:connaissances?|capacit[eé]s?|aptitudes?|savoir|[eê]tre capable) (?:de la |de l'|des |du |de |d'|à |a |au |aux |en )" +
  "|(?:ma[iî]trise|notions?) (?:de la |de l'|des |du |de |d'|à |a |au |aux |en )?)",
  "u",
);
const EXIGENCE = new RegExp(
  `[\\s(]+(?:indispensables?|appr[eé]ci[eé]${W}*|souhait[eé]${W}*|serait un (?:atout|plus)|un plus|requis${W}*|exig[eé]${W}*)\\)?$`,
  "u",
);

/** `str.strip(caracteres)` de Python. */
function retirer(texte, caracteres, debut = true, fin = true) {
  let i = 0;
  let j = texte.length;
  if (debut) while (i < j && caracteres.includes(texte[i])) i++;
  if (fin) while (j > i && caracteres.includes(texte[j - 1])) j--;
  return texte.slice(i, j);
}

export function sansAccents(texte) {
  return texte.normalize("NFKD").replace(/\p{Mn}/gu, "");
}

export function formeBrute(texte) {
  return sansAccents(texte.toLowerCase()).replace(/[^a-z0-9+#]+/g, " ").replace(/\s+/g, " ").trim();
}

/** Item lisible : minuscules, sans « bonne connaissance de », « capacité à »... ni mentions d'exigence. */
export function nettoyer(texte) {
  let t = retirer(texte.toLowerCase().replaceAll("’", "'").replace(ESPACES_RE, " "), " .,;:-");
  t = t.replace(EXIGENCE, "");
  const reste = t.replace(PREFIXE, "");
  return reste.length >= 3 ? reste : t;
}

/** Forme de comparaison : `nettoyer`, puis sans accents ni ponctuation. */
export function normaliser(texte) {
  return formeBrute(nettoyer(texte));
}

const longueur = (texte) => [...texte].length; // en caractères, comme `len` en Python

/** Texte libre → items de compétence (une ligne, une puce, ou un élément d'une liste à virgules). */
export function segmenter(texte) {
  if (!texte) return [];
  const items = [];
  for (let ligne of texte.split(/[\r\n\t]+|;|•||/)) {
    ligne = retirer(retirer(ligne.replace(PUCE, ""), " ,:\t-"), ".", false, true);
    if (ligne.includes(":")) {
      const k = ligne.indexOf(":");
      const tete = ligne.slice(0, k);
      const reste = ligne.slice(k + 1);
      if (NIVEAU_ENTIER.test(formeBrute(reste))) {
        ligne = retirer(tete, ESPACES);
      } else if (TITRE.test(formeBrute(tete)) || NIVEAU.test(formeBrute(tete)) || mots(tete).length <= 3) {
        ligne = retirer(reste, " .,");
      }
    }
    const forme = formeBrute(ligne);
    if (!ligne || TITRE.test(forme) || NIVEAU_ENTIER.test(forme) || RENVOI.test(forme)) continue;
    const morceaux = ligne.split(/(?<!\d),|,(?!\d)/).map((m) => retirer(retirer(m, ESPACES), ".", false, true));
    if (morceaux.length > 1 && morceaux.every((m) => mots(m).length > 0 && mots(m).length <= 4)) {
      items.push(...morceaux.filter(Boolean));
    } else {
      items.push(ligne);
    }
  }
  return items.filter((i) => longueur(i) >= 3 && longueur(i) <= 200);
}

/** N-grammes de caractères de 3 à 5 par mot bordé d'espaces (`analyzer="char_wb"` de scikit-learn). */
export function ngrammes(texte) {
  const resultat = [];
  for (const mot of texte.toLowerCase().split(/\s+/).filter(Boolean)) {
    // Les formes normalisées sont en ASCII : découpe directe ; sinon, par caractère Unicode comme Python
    const w = /^[\x00-\x7f]*$/.test(mot) ? ` ${mot} ` : [...` ${mot} `];
    const morceau = typeof w === "string" ? (a, b) => w.slice(a, b) : (a, b) => w.slice(a, b).join("");
    for (let n = 3; n <= 5; n++) {
      let debut = 0;
      resultat.push(morceau(0, n));
      while (debut + n < w.length) {
        debut += 1;
        resultat.push(morceau(debut, debut + n));
      }
      if (debut === 0) break; // mot court : compté une seule fois, comme scikit-learn
    }
  }
  return resultat;
}

/** TF-IDF « sublinéaire », normé, ajusté sur les formes du catalogue ; `chercher` renvoie les meilleures entrées. */
export class Tfidf {
  constructor(formes) {
    const n = (this.n = formes.length);
    const vocabulaire = (this.vocabulaire = new Map());
    // 1. N-grammes de chaque forme, en identifiants
    const ids = [];
    const debutForme = new Int32Array(n + 1);
    formes.forEach((forme, i) => {
      for (const g of ngrammes(forme)) {
        let j = vocabulaire.get(g);
        if (j === undefined) vocabulaire.set(g, (j = vocabulaire.size));
        ids.push(j);
      }
      debutForme[i + 1] = ids.length;
    });
    const v = vocabulaire.size;
    // 2. Termes distincts et fréquences par forme ; nombre de formes par terme (df)
    const vu = new Int32Array(v).fill(-1);
    const position = new Int32Array(v);
    const termes = new Int32Array(ids.length);
    const tf = new Float64Array(ids.length);
    const debut = new Int32Array(n + 1);
    const df = new Float64Array(v);
    let m = 0;
    for (let i = 0; i < n; i++) {
      for (let k = debutForme[i]; k < debutForme[i + 1]; k++) {
        const j = ids[k];
        if (vu[j] !== i) {
          vu[j] = i;
          position[j] = m;
          termes[m] = j;
          tf[m++] = 1;
          df[j] += 1;
        } else {
          tf[position[j]] += 1;
        }
      }
      debut[i + 1] = m;
    }
    this.idf = Float64Array.from(df, (d) => Math.log((1 + n) / (1 + d)) + 1);
    // 3. Poids normés de chaque forme, rangés par terme (index inversé en lignes compressées)
    this.debut = new Int32Array(v + 1);
    for (let k = 0; k < m; k++) this.debut[termes[k] + 1] += 1;
    for (let j = 0; j < v; j++) this.debut[j + 1] += this.debut[j];
    const curseur = this.debut.slice(0, v);
    this.entrees = new Int32Array(m);
    this.poids = new Float32Array(m);
    for (let i = 0; i < n; i++) {
      const p = this.#ponderer(termes.subarray(debut[i], debut[i + 1]), tf.subarray(debut[i], debut[i + 1]));
      for (let k = debut[i]; k < debut[i + 1]; k++) {
        const pos = curseur[termes[k]]++;
        this.entrees[pos] = i;
        this.poids[pos] = p[k - debut[i]];
      }
    }
    this.scores = new Float32Array(n);
  }

  #ponderer(termes, tfs) {
    const p = new Float64Array(termes.length);
    let norme = 0;
    for (let k = 0; k < termes.length; k++) {
      p[k] = (1 + Math.log(tfs[k])) * this.idf[termes[k]];
      norme += p[k] * p[k];
    }
    norme = Math.sqrt(norme) || 1;
    for (let k = 0; k < p.length; k++) p[k] /= norme;
    return p;
  }

  /** Les `k` entrées du catalogue les plus proches de la forme, avec leur similarité cosinus. */
  chercher(forme, k = 1) {
    const c = new Map();
    for (const g of ngrammes(forme)) {
      const j = this.vocabulaire.get(g);
      if (j !== undefined) c.set(j, (c.get(j) ?? 0) + 1);
    }
    const termes = Int32Array.from(c.keys());
    const q = this.#ponderer(termes, Float64Array.from(c.values()));
    const scores = this.scores;
    const touches = [];
    for (let t = 0; t < termes.length; t++) {
      for (let pos = this.debut[termes[t]]; pos < this.debut[termes[t] + 1]; pos++) {
        const i = this.entrees[pos];
        if (scores[i] === 0) touches.push(i);
        scores[i] += q[t] * this.poids[pos];
      }
    }
    // Les k meilleurs sans trier toutes les entrées touchées (à score égal, la première du catalogue)
    const meilleurs = [];
    for (const i of touches) {
      const s = scores[i];
      scores[i] = 0;
      const dernier = meilleurs[k - 1];
      if (dernier && (s < dernier[1] || (s === dernier[1] && i > dernier[0]))) continue;
      let r = meilleurs.length;
      while (r > 0 && (s > meilleurs[r - 1][1] || (s === meilleurs[r - 1][1] && i < meilleurs[r - 1][0]))) r--;
      meilleurs.splice(r, 0, [i, s]);
      if (meilleurs.length > k) meilleurs.pop();
    }
    return meilleurs;
  }
}
