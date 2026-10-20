// Tableau de bord : filtres (métier, territoire, année), indicateurs, série mensuelle, carte des départements,
// compétences citées et fiche ROME. Toutes les sommes se font ici, à partir des comptes par département et par année.

(async function () {
  const { charger, objets, nombre, pourcent, date, MOIS, echapper, montrerBulle, cacherBulle } = Commun;
  const $ = (id) => document.getElementById(id);
  const SVG = "http://www.w3.org/2000/svg";
  const MIN_PART = 20; // en dessous de 20 offres renseignées, une part n'est pas montrée (carte et tuiles)

  let resume, metiers, territoires, geo;
  try {
    [resume, metiers, territoires, geo] = await Promise.all([
      charger("donnees/resume"), charger("donnees/metiers"), charger("donnees/territoires"), charger("geo/departements"),
    ]);
  } catch (erreur) {
    $("selection").textContent = `Données indisponibles (${erreur.message}).`;
    return;
  }
  metiers = objets(metiers);
  const parId = new Map(metiers.map((m) => [m.id, m]));
  const parNom = new Map(metiers.map((m) => [m.metier.toLowerCase(), m]));
  const K = Object.fromEntries(resume.colonnes_kpi.map((c, i) => [c, i]));
  const annees = [];
  for (let a = Number(resume.debut.slice(0, 4)); a <= Number(resume.fin.slice(0, 4)); a++) annees.push(String(a));
  const departements = territoires.departements;

  $("couverture").textContent =
    `${nombre(resume.offres)} offres de la fonction publique publiées sur Choisir le service public, de janvier 2022 au ` +
    `${date(resume.fin)}, pour ${nombre(resume.metiers)} métiers.`;
  $("maj").textContent = `Mis à jour le ${date(resume.mise_a_jour)}.`;
  $("fin-rep").textContent = date(resume.republication_fin);

  // Filtres
  $("liste-metiers").innerHTML = metiers.map((m) => `<option value="${echapper(m.metier)}"></option>`).join("");
  const optRegions = territoires.regions.map((r) => `<option value="r:${echapper(r)}">${echapper(r)}</option>`).join("");
  const optDeps = territoires.regions.map((r) => {
    const deps = Object.entries(departements).filter(([, d]) => d.region === r);
    return `<optgroup label="${echapper(r)}">${deps.map(([c, d]) => `<option value="${c}">${echapper(d.nom)} (${c})</option>`).join("")}</optgroup>`;
  }).join("");
  $("territoire").insertAdjacentHTML("beforeend", `<optgroup label="Régions">${optRegions}</optgroup>${optDeps}`);
  const finMois = Number(resume.fin.slice(5, 7));
  $("annee").insertAdjacentHTML("beforeend", annees.map((a) =>
    `<option value="${a}">${a}${a === annees.at(-1) && finMois < 12 ? ` (jusqu'à ${MOIS[finMois - 1]})` : ""}</option>`).join(""));

  const etat = { metier: 0, territoire: "", annee: "", mesure: "n" };
  const lireAdresse = () => {
    const p = new URLSearchParams(location.hash.slice(1));
    etat.metier = parId.has(Number(p.get("m"))) ? Number(p.get("m")) : 0;
    const t = p.get("t") ?? "";
    etat.territoire = t === "" || departements[t] || territoires.regions.includes(t.slice(2)) ? t : "";
    etat.annee = annees.includes(p.get("a")) ? p.get("a") : "";
    etat.mesure = ["n", "tt", "rep"].includes(p.get("c")) ? p.get("c") : "n";
  };
  const ecrireAdresse = () => {
    const p = new URLSearchParams();
    if (etat.metier) p.set("m", etat.metier);
    if (etat.territoire) p.set("t", etat.territoire);
    if (etat.annee) p.set("a", etat.annee);
    if (etat.mesure !== "n") p.set("c", etat.mesure);
    history.replaceState(null, "", p.size ? `#${p}` : location.pathname);
  };

  const fichiers = new Map();
  const donneesMetier = (id) => {
    if (!fichiers.has(id)) fichiers.set(id, charger(`donnees/metiers/${id}`));
    return fichiers.get(id);
  };

  // Sommes
  const depsDe = (territoire) => {
    if (!territoire) return null; // France entière, départements inconnus compris
    if (territoire.startsWith("r:")) return Object.keys(departements).filter((c) => departements[c].region === territoire.slice(2));
    return [territoire];
  };
  function somme(d, deps, annee) {
    const total = new Array(resume.colonnes_kpi.length).fill(0);
    for (const dep of deps ?? Object.keys(d.territoires)) {
      const t = d.territoires[dep];
      if (!t) continue;
      for (const [a, valeurs] of Object.entries(t.annees)) {
        if (annee && a !== annee) continue;
        valeurs.forEach((v, i) => (total[i] += v));
      }
    }
    return total;
  }
  function serie(d, deps) {
    const total = new Array(resume.nb_mois).fill(0);
    for (const dep of deps ?? Object.keys(d.territoires)) d.territoires[dep]?.serie.forEach((v, i) => (total[i] += v));
    return total;
  }
  const part = (num, den) => (den >= MIN_PART ? num / den : null);
  function valeur(k, mesure) {
    if (mesure === "n") return { v: k[K.n], n: k[K.n] };
    if (mesure === "tt") return { v: part(k[K.tt], k[K.tt_r]), n: k[K.tt_r] };
    return { v: part(k[K.rep], k[K.rep_r]), n: k[K.rep_r] };
  }
  const nomTerritoire = (t) => (!t ? "France entière" : t.startsWith("r:") ? t.slice(2) : `${departements[t].nom} (${t})`);

  // Rendu
  async function rendre() {
    ecrireAdresse();
    $("metier").value = etat.metier ? parId.get(etat.metier).metier : "";
    $("territoire").value = etat.territoire;
    $("annee").value = etat.annee;
    $("mesure").value = etat.mesure;
    const d = await donneesMetier(etat.metier);
    const deps = depsDe(etat.territoire);
    const k = somme(d, deps, etat.annee);
    const nomMetier = etat.metier ? parId.get(etat.metier).metier : "Tous les métiers";
    const morceaux = [nomMetier, nomTerritoire(etat.territoire), etat.annee || "2022 à 2026"];
    const filtre = etat.metier || etat.territoire || etat.annee;
    $("selection").innerHTML = `${morceaux.map(echapper).join(" · ")}${filtre ? ' <button type="button" id="effacer">Tout effacer</button>' : ""}`;
    $("effacer")?.addEventListener("click", () => Object.assign(etat, { metier: 0, territoire: "", annee: "" }) && rendre());
    tuiles(k, d);
    courbe(serie(d, deps));
    carte(d);
    competences(d);
    fiche(d);
  }

  function tuiles(k, d) {
    $("k-offres").textContent = nombre(k[K.n]);
    const toutes = somme(d, null, "")[K.n];
    $("k-offres-note").textContent = etat.territoire || etat.annee
      ? `${pourcent(k[K.n] / toutes, 1)} des offres de ce métier sur 2022-2026`
      : etat.metier ? `${pourcent(k[K.n] / resume.offres, 1)} de toutes les offres` : "toutes les offres depuis 2022";
    const tt = part(k[K.tt], k[K.tt_r]);
    $("k-tt").textContent = pourcent(tt);
    $("k-tt-note").textContent = k[K.n] ? `champ renseigné pour ${pourcent(k[K.tt_r] / k[K.n])} des offres` : "";
    const a = k[K["cat_A+"]] + k[K.cat_A];
    const cats = [a, k[K.cat_B], k[K.cat_C]];
    const totalCat = cats.reduce((x, y) => x + y, 0);
    $("k-cat").textContent = totalCat ? cats.map((c) => pourcent(c / totalCat)).join(" · ") : "–";
    $("k-cat-pile").innerHTML = totalCat
      ? cats.map((c, i) => `<i style="flex:${c};background:var(${["--bleu", "--orange", "--aqua"][i]})"></i>`).join("")
      : "";
    $("k-mg").textContent = pourcent(part(k[K.mg], k[K.mg_r]));
    $("k-mg-note").textContent = k[K.n] ? `champ renseigné pour ${pourcent(k[K.mg_r] / k[K.n])} des offres` : "";
    const rep = part(k[K.rep], k[K.rep_r]);
    $("k-rep").textContent = pourcent(rep);
    $("k-rep-note").textContent = k[K.rep_r] >= MIN_PART
      ? `sur ${nombre(k[K.rep_r])} annonces publiées jusqu'au ${date(resume.republication_fin)}`
      : "trop peu d'annonces pour un taux";
  }

  function graduations(max) {
    const brut = max / 4;
    const puissance = 10 ** Math.floor(Math.log10(brut || 1));
    const pas = [1, 2, 2.5, 5, 10].map((m) => m * puissance).find((p) => p >= brut);
    const ticks = [];
    for (let v = 0; v <= max + 1e-9; v += pas) ticks.push(v);
    if (ticks.at(-1) < max) ticks.push(ticks.at(-1) + pas);
    return ticks;
  }

  function courbe(valeurs) {
    // Le repère suit la largeur réelle du panneau : le texte garde sa taille sur téléphone
    const l = Math.max(300, Math.round($("serie").clientWidth || 900)), h = l < 600 ? 220 : 250, g = 52, dr = 12, ha = 16, ba = 26;
    const ticks = graduations(Math.max(...valeurs, 1));
    const ymax = ticks.at(-1);
    const x = (i) => g + (i * (l - g - dr)) / (valeurs.length - 1);
    const y = (v) => ha + (h - ha - ba) * (1 - v / ymax);
    const debut = Number(resume.debut.slice(0, 4));
    let html = `<svg viewBox="0 0 ${l} ${h}" role="img" aria-label="Offres publiées chaque mois">`;
    if (etat.annee) {
      const i0 = (Number(etat.annee) - debut) * 12;
      const i1 = Math.min(i0 + 11, valeurs.length - 1);
      html += `<rect class="annee-choisie" x="${x(i0) - 4}" y="${ha}" width="${x(i1) - x(i0) + 8}" height="${h - ha - ba}"/>`;
    }
    html += '<g class="axe">';
    for (const t of ticks) html += `<line x1="${g}" x2="${l - dr}" y1="${y(t)}" y2="${y(t)}"/><text x="${g - 8}" y="${y(t) + 4}" text-anchor="end">${nombre(t)}</text>`;
    for (let i = 0; i < valeurs.length; i += 12) html += `<text x="${x(i)}" y="${h - 6}" text-anchor="${i ? "middle" : "start"}">${debut + i / 12}</text>`;
    html += "</g>";
    const pts = valeurs.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
    html += `<path class="aire-serie" d="M${x(0)},${y(0)}L${pts.join("L")}L${x(valeurs.length - 1)},${y(0)}Z"/>`;
    html += `<path class="ligne-serie" d="M${pts.join("L")}"/>`;
    html += `<g class="repere" hidden><line y1="${ha}" y2="${h - ba}"/><circle r="4"/></g>`;
    html += `<rect x="${g}" y="0" width="${l - g - dr}" height="${h}" fill="transparent" class="zone"/></svg>`;
    const conteneur = $("serie");
    conteneur.innerHTML = html;
    const svg = conteneur.querySelector("svg");
    const repere = svg.querySelector(".repere");
    svg.querySelector(".zone").addEventListener("pointermove", (e) => {
      const r = svg.getBoundingClientRect();
      const px = ((e.clientX - r.left) * l) / r.width;
      const i = Math.max(0, Math.min(valeurs.length - 1, Math.round(((px - g) * (valeurs.length - 1)) / (l - g - dr))));
      repere.hidden = false;
      repere.querySelector("line").setAttribute("x1", x(i));
      repere.querySelector("line").setAttribute("x2", x(i));
      repere.querySelector("circle").setAttribute("cx", x(i));
      repere.querySelector("circle").setAttribute("cy", y(valeurs[i]));
      montrerBulle(e, `${MOIS[i % 12]} ${debut + Math.floor(i / 12)}<br><b>${nombre(valeurs[i])}</b> offres`);
    });
    svg.querySelector(".zone").addEventListener("pointerleave", () => { repere.hidden = true; cacherBulle(); });
    const parties = [etat.metier ? parId.get(etat.metier).metier : "tous les métiers", nomTerritoire(etat.territoire)];
    $("serie-titre").textContent = `${parties[1]}, ${parties[0].charAt(0).toLowerCase() + parties[0].slice(1)}`;
  }

  // Palette séquentielle bleue (pas 100 à 650), en sens inverse sur fond sombre : le faible se fond dans le fond
  const RAMPE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#104281"];
  const sombre = matchMedia("(prefers-color-scheme: dark)");
  const couleur = (t) => {
    const rampe = sombre.matches ? [...RAMPE].reverse() : RAMPE;
    const p = Math.max(0, Math.min(1, t)) * (rampe.length - 1);
    const i = Math.min(Math.floor(p), rampe.length - 2);
    const melange = (a, b, f) => Math.round(a + (b - a) * f);
    const [c1, c2] = [rampe[i], rampe[i + 1]].map((c) => [1, 3, 5].map((j) => parseInt(c.slice(j, j + 2), 16)));
    return `rgb(${c1.map((v, j) => melange(v, c2[j], p - i)).join(",")})`;
  };
  const GRIS = () => (sombre.matches ? "#33332f" : "#e4e3df");

  function carte(d) {
    const mesure = etat.mesure;
    const valeurs = {};
    for (const code of Object.keys(departements)) {
      const t = d.territoires[code];
      valeurs[code] = t ? valeur(somme(d, [code], etat.annee), mesure) : { v: mesure === "n" ? 0 : null, n: 0 };
    }
    const connues = Object.values(valeurs).map((x) => x.v).filter((v) => v !== null);
    const max = Math.max(...connues, mesure === "n" ? 1 : 0.01);
    const min = mesure === "n" ? 0 : Math.min(...connues, max);
    // Les volumes, très concentrés (Paris, Nord), sont colorés en racine carrée pour garder du relief ailleurs
    const echelle = (v) => (mesure === "n" ? Math.sqrt(v / max) : (v - min) / (max - min || 1));
    const fond = (v) => (v === null ? GRIS() : couleur(echelle(v)));
    const texte = (x) => (mesure === "n" ? `${nombre(x.v)} offres` : x.v === null ? `trop peu de données (${nombre(x.n)})` :
      `${pourcent(x.v)} sur ${nombre(x.n)} ${mesure === "tt" ? "offres renseignées" : "annonces"}`);
    const choisis = new Set(depsDe(etat.territoire) ?? []);

    let html = `<svg viewBox="0 0 ${geo.largeur} ${geo.hauteur}" role="img" aria-label="Carte des départements">`;
    for (const [code, dep] of Object.entries(geo.departements)) {
      html += `<path d="${dep.d}" data-code="${code}" fill="${fond(valeurs[code]?.v ?? null)}"${choisis.has(code) ? ' class="choisi"' : ""}/>`;
    }
    $("carte").innerHTML = `${html}</svg>`;
    const om = Object.keys(departements).filter((c) => departements[c].region === "Outre-mer" && d.territoires[c]);
    $("outre-mer").innerHTML = om.map((c) =>
      `<button type="button" data-code="${c}" class="${choisis.has(c) ? "choisi" : ""}"><i style="background:${fond(valeurs[c].v)}"></i>${echapper(departements[c].nom)}</button>`).join("");
    const libelle = { n: "Offres", tt: "Part avec télétravail possible", rep: "Part de postes republiés" }[mesure];
    const fin = (v) => (mesure === "n" ? nombre(v) : pourcent(v));
    const pas = Array.from({ length: 8 }, (_, i) => couleur(i / 7)).join(",");
    $("legende-carte").innerHTML = `<span>${fin(min)}</span><span class="degrade" style="background:linear-gradient(90deg,${pas})"></span><span>${fin(max)}</span>` +
      (mesure === "n" ? "<span>(échelle en racine carrée)</span>" : `<span><i class="vide" style="background:${GRIS()}"></i> moins de ${MIN_PART} offres renseignées</span>`);
    $("table-carte").innerHTML = `<thead><tr><th>Département</th><th>${libelle}</th></tr></thead><tbody>` +
      Object.entries(valeurs).filter(([c]) => d.territoires[c]).sort((a, b) => (b[1].v ?? -1) - (a[1].v ?? -1))
        .map(([c, x]) => `<tr><td>${echapper(departements[c].nom)} (${c})</td><td>${x.v === null ? "–" : fin(x.v)}</td></tr>`).join("") + "</tbody>";

    for (const el of document.querySelectorAll("#carte path, #outre-mer button")) {
      const code = el.dataset.code;
      el.addEventListener("pointermove", (e) => montrerBulle(e, `<b>${echapper(departements[code]?.nom ?? code)}</b><br>${texte(valeurs[code])}`));
      el.addEventListener("pointerleave", cacherBulle);
      el.addEventListener("click", () => {
        cacherBulle();
        etat.territoire = etat.territoire === code ? "" : code;
        rendre();
      });
    }
  }

  function competences(d) {
    const c = d.competences;
    const alerte = $("competences-alerte");
    alerte.hidden = true;
    if (!c.liste) {
      $("competences-titre").textContent = "";
      $("competences").innerHTML = `<p class="discret petit">Seules ${nombre(c.textes)} annonces de ce métier ont un texte de compétences : trop peu pour une liste fiable. La fiche ROME ci-contre donne les compétences de référence du métier.</p>`;
      return;
    }
    $("competences-titre").textContent =
      `Part des ${nombre(c.textes)} annonces avec un texte qui citent chaque compétence (2022-2026, tous territoires).`;
    const max = c.liste[0][2];
    $("competences").innerHTML = c.liste.slice(0, 15).map(([libelle, domaine, p]) =>
      `<div class="barre"><span class="nom" title="${echapper(libelle)}">${echapper(libelle)}<small>${echapper(domaine)}</small></span>` +
      `<span class="piste"><span class="remplissage" style="width:${(100 * p) / max}%"></span></span><span class="valeur">${pourcent(p)}</span></div>`).join("");
    if (c.part_employeur >= 0.4) {
      alerte.hidden = false;
      alerte.textContent = `${pourcent(c.part_employeur)} de ces textes viennent d'un seul employeur (${c.employeur}) : la liste reflète d'abord ses fiches de poste.`;
    }
  }

  async function fiche(d) {
    if (!etat.metier) {
      const zero = await donneesMetier(0);
      const cle = `${etat.territoire || "France"}|${etat.annee || "toutes"}`;
      const liste = zero.metiers_frequents[cle] ?? [];
      $("fiche-titre").textContent = "Métiers les plus fréquents";
      $("fiche-sous-titre").textContent = `${nomTerritoire(etat.territoire)}, ${etat.annee || "2022 à 2026"}. Cliquez pour filtrer.`;
      $("fiche").innerHTML = `<ul class="liste-metiers">${liste.map(([id, n]) =>
        `<li><button type="button" data-id="${id}"><span>${echapper(parId.get(id).metier)}</span><span>${nombre(n)}</span></button></li>`).join("")}</ul>`;
      for (const b of $("fiche").querySelectorAll("button")) b.addEventListener("click", () => { etat.metier = Number(b.dataset.id); rendre(); });
      return;
    }
    $("fiche-titre").textContent = "Fiche ROME rattachée";
    const f = d.fiche;
    if (!f) {
      $("fiche-sous-titre").textContent = "";
      $("fiche").innerHTML = '<p class="discret petit">Pas de fiche ROME rattachée à ce métier.</p>';
      return;
    }
    $("fiche-sous-titre").innerHTML = `Rapprochement automatique par l'intitulé, via l'appellation « ${echapper(f.appellation)} ».`;
    $("fiche").innerHTML = `<p><span class="fiche-code">${f.code_rome}</span><a href="https://candidat.francetravail.fr/metierscope/fiche-metier/${f.code_rome}" target="_blank" rel="noopener">${echapper(f.libelle)}</a></p>` +
      (f.coeur.length ? `<p class="petit discret" style="margin:12px 0 0">Compétences du cœur de métier selon le ROME :</p><ul class="coeur">${f.coeur.map((c) => `<li>${echapper(c)}</li>`).join("")}</ul>` : "");
  }

  // Événements
  $("metier").addEventListener("change", () => {
    const m = parNom.get($("metier").value.trim().toLowerCase());
    etat.metier = m ? m.id : 0;
    rendre();
  });
  $("metier").addEventListener("search", () => { if (!$("metier").value) { etat.metier = 0; rendre(); } });
  $("territoire").addEventListener("change", () => { etat.territoire = $("territoire").value; rendre(); });
  $("annee").addEventListener("change", () => { etat.annee = $("annee").value; rendre(); });
  $("mesure").addEventListener("change", () => { etat.mesure = $("mesure").value; rendre(); });
  window.addEventListener("hashchange", () => { lireAdresse(); rendre(); });
  sombre.addEventListener("change", () => rendre());
  let attente;
  let largeur = $("serie").clientWidth;
  window.addEventListener("resize", () => {
    clearTimeout(attente);
    attente = setTimeout(() => { if ($("serie").clientWidth !== largeur) { largeur = $("serie").clientWidth; rendre(); } }, 200);
  });
  lireAdresse();
  rendre();
})();
