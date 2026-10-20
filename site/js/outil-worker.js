// Travail de fond de l'outil « Mes compétences » : charge le référentiel ROME, construit l'index TF-IDF (deux secondes
// environ) sans bloquer la page, puis découpe et rapproche chaque texte reçu.

import { normaliser, segmenter, Tfidf } from "./extraction.js";

const SEUIL_PROCHE = 0.8; // TF-IDF : 3 rapprochements sur 4 exacts au-dessus, sur l'échantillon annoté du notebook 02
const SEUIL_INCERTAIN = 0.5; // en dessous, presque jamais exact (4 %) : l'item est montré à part

const charger = (nom) => fetch(new URL(`../outil/${nom}.json`, import.meta.url)).then((r) => {
  if (!r.ok) throw new Error(`${nom}.json : ${r.status}`);
  return r.json();
});

const pret = (async () => {
  const [catalogue, formes, fiches] = await Promise.all([charger("catalogue"), charger("formes"), charger("fiches")]);
  const index = new Tfidf(catalogue.libelles.map(normaliser));
  const vues = new Map(formes.formes.map((f, i) => [f, [formes.entrees[i], formes.occurrences[i]]]));
  const lignes = fiches.lignes.map(([code, libelle, coeur, autres, metiers]) => ({
    code, libelle, coeur, metiers, toutes: new Set([...coeur, ...autres]),
  }));
  // Poids d'une compétence pour comparer aux fiches : rare dans les fiches, elle compte plus (idf)
  const df = new Map();
  for (const f of lignes) for (const e of f.toutes) df.set(e, (df.get(e) ?? 0) + 1);
  const poids = (e) => Math.log((1 + lignes.length) / (1 + (df.get(e) ?? 0)));
  for (const f of lignes) f.norme = Math.sqrt([...f.toutes].reduce((s, e) => s + poids(e) ** 2, 0)) || 1;
  return { catalogue, index, vues, lignes, poids, formes: formes.formes.length, transversales: new Set(catalogue.transversales) };
})();

function rapprocher({ catalogue, index, vues }, item) {
  const forme = normaliser(item);
  if (forme.length < 2) return null;
  const vue = vues.get(forme);
  const resultat = (entree, extra) => ({
    item, entree, libelle: catalogue.libelles[entree], domaine: catalogue.domaines[catalogue.domaine[entree]],
    macro: catalogue.macro[entree], ...extra,
  });
  if (vue) return resultat(vue[0], { source: "vue", occurrences: vue[1] });
  const [meilleur] = index.chercher(forme, 1);
  if (!meilleur) return { item, entree: null, source: "aucun", score: 0 };
  const [entree, score] = meilleur;
  const niveau = score >= SEUIL_PROCHE ? "proche" : score >= SEUIL_INCERTAIN ? "approximatif" : "incertain";
  return resultat(entree, { source: "tfidf", score, niveau });
}

function fichesProches({ lignes, poids, catalogue }, entrees, n = 5) {
  // Similarité cosinus entre l'ensemble des compétences du texte et celui de chaque fiche, chaque compétence pesant
  // son idf : partager une compétence rare compte plus que partager « travail en équipe »
  const norme = Math.sqrt([...entrees].reduce((s, e) => s + poids(e) ** 2, 0)) || 1;
  return lignes
    .map((f) => {
      const communes = [...entrees].filter((e) => f.toutes.has(e));
      const score = communes.reduce((s, e) => s + poids(e) ** 2, 0) / (norme * f.norme);
      return { f, communes, score };
    })
    .filter((x) => x.communes.length >= 2)
    .sort((a, b) => b.score - a.score)
    .slice(0, n)
    .map(({ f, communes, score }) => ({
      code: f.code, libelle: f.libelle, score, metiers: f.metiers,
      communes: communes.map((e) => catalogue.libelles[e]),
      manquantes: f.coeur.filter((e) => !entrees.has(e)).slice(0, 8).map((e) => catalogue.libelles[e]),
    }));
}

self.onmessage = async ({ data }) => {
  try {
    const etat = await pret;
    if (data.type === "pret") {
      self.postMessage({ type: "pret", competences: etat.catalogue.libelles.length, formes: etat.formes, fiches: etat.lignes.length });
      return;
    }
    const items = [...new Set(segmenter(data.texte))];
    const resultats = items.map((i) => rapprocher(etat, i)).filter(Boolean);
    // Les compétences demandées partout (rigueur, travail en équipe...) ne disent rien du métier : écartées ici
    const distinctives = new Set(resultats.filter((r) => r.entree !== null && r.niveau !== "incertain" &&
      !etat.transversales.has(r.entree)).map((r) => r.entree));
    for (const r of resultats) r.transversale = etat.transversales.has(r.entree);
    self.postMessage({ type: "resultats", id: data.id, resultats, fiches: fichesProches(etat, distinctives) });
  } catch (erreur) {
    self.postMessage({ type: "erreur", message: String(erreur.message ?? erreur) });
  }
};
