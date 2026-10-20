// Page « Coulisses » : chaîne de traitements (état lu en direct sur GitHub), contrôles des données, dérive des
// compétences. Les rapports viennent du workflow « Suivi » (donnees/suivi_dernier.json, donnees/suivi_historique.json).

(async function () {
  const { charger, nombre, pourcent, date, MOIS, echapper, montrerBulle, cacherBulle } = Commun;
  const $ = (id) => document.getElementById(id);
  const DEPOT = "nitescuale/offres-emploi-competences";

  const NIVEAUX = {
    ok: { libelle: "OK", icone: "✓" },
    alerte: { libelle: "Alerte", icone: "!" },
    erreur: { libelle: "Erreur", icone: "✕" },
  };
  const pastille = (niveau, texte) =>
    `<span class="statut n-${niveau}"><span class="icone" aria-hidden="true">${NIVEAUX[niveau].icone}</span>${texte ?? NIVEAUX[niveau].libelle}</span>`;

  // --- Chaîne de traitements ---------------------------------------------------------------------------------------
  const CHAINE = [
    ["csp.yml", "Offres Choisir le service public", "Chaque lundi : les fichiers annuels de data.gouv.fr, normalisés en un seul Parquet. Refuse de publier un fichier amputé."],
    ["competences.yml", "Compétences", "Après chaque mise à jour des offres : textes découpés, items rattachés au ROME (seules les formes nouvelles sont calculées)."],
    ["suivi.yml", "Suivi", "Chaque nuit et après les compétences : les contrôles et la dérive présentés sur cette page."],
    ["site.yml", "Site", "Après chaque suivi : données du tableau de bord et de l'outil recalculées, site publié."],
    ["collecte.yml", "Collecte France Travail", "Chaque jour : prête, en attente d'un accès à l'API Offres d'emploi, devenue restreinte."],
    ["ci.yml", "Tests", "À chaque modification du code : tests, dont la parité du JavaScript de l'outil avec le Python."],
  ];
  const idWorkflow = (fichier) => `w-${fichier.replace(".yml", "")}`;
  $("chaine").innerHTML = CHAINE.map(([fichier, nom, texte]) => `
    <li>
      <div><b>${nom}</b><p class="petit discret">${texte}</p></div>
      <a class="passage" id="${idWorkflow(fichier)}" href="https://github.com/${DEPOT}/actions/workflows/${fichier}">…</a>
    </li>`).join("");
  const heure = (iso) => new Date(iso).toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  // Un seul appel (l'API GitHub sans compte accepte 60 appels par heure), limité à main : pas les essais des PR
  fetch(`https://api.github.com/repos/${DEPOT}/actions/runs?branch=main&per_page=100`)
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then(({ workflow_runs: runs }) => {
      for (const [fichier] of CHAINE) {
        const lien = $(idWorkflow(fichier));
        const run = runs.find((x) => x.path === `.github/workflows/${fichier}`);
        if (!run) { lien.textContent = "voir sur GitHub"; continue; }
        lien.href = run.html_url;
        if (run.status !== "completed") { lien.innerHTML = `<span class="statut cours">en cours</span>`; continue; }
        const niveau = run.conclusion === "success" ? "ok" : run.conclusion === "failure" ? "erreur" : "alerte";
        const mot = { success: "réussi", failure: "échoué", cancelled: "annulé", skipped: "ignoré" }[run.conclusion] ?? run.conclusion;
        lien.innerHTML = `${pastille(niveau, mot)}<small>${heure(run.updated_at)}</small>`;
      }
    })
    .catch(() => { for (const [fichier] of CHAINE) $(idWorkflow(fichier)).textContent = "voir sur GitHub"; });

  // --- Rapports du suivi --------------------------------------------------------------------------------------------
  let rapport;
  try {
    rapport = await charger("donnees/suivi_dernier");
  } catch {
    $("sans-controle").hidden = false;
    $("statut-global").hidden = true;
    return;
  }
  const historique = await charger("donnees/suivi_historique").catch(() => []);
  const controle = Object.fromEntries(rapport.controles.map((c) => [c.code, c]));

  $("statut-global").outerHTML = pastille(rapport.statut);
  const maj = rapport.source?.mise_a_jour_fichier ? ` · fichier de l'année mis à jour le ${date(rapport.source.mise_a_jour_fichier)}` : "";
  $("controles-date").textContent = `Contrôle du ${date(rapport.date)} · ${nombre(rapport.offres)} offres, la dernière publiée le ${date(rapport.derniere_publication)}${maj}`;
  const ordre = { erreur: 0, alerte: 1, ok: 2 };
  $("controles").innerHTML = "<thead><tr><th>Contrôle</th><th>État</th><th>Détail</th></tr></thead><tbody>" +
    [...rapport.controles].sort((a, b) => ordre[a.niveau] - ordre[b.niveau]).map((c) =>
      `<tr><td>${echapper(c.libelle)}</td><td>${pastille(c.niveau)}</td><td class="discret">${echapper(c.detail)}</td></tr>`).join("") +
    "</tbody>";

  const jours = historique.slice(-90).filter((j) => NIVEAUX[j.statut]);
  if (jours.length > 1) {
    $("historique-bloc").hidden = false;
    const nb = (n) => jours.filter((j) => j.statut === n).length;
    $("historique-titre").textContent = `${jours.length} derniers contrôles : ${nb("ok")} sans alerte, ${nb("alerte")} avec alerte, ${nb("erreur")} en erreur.`;
    const libelleJour = (j) => `${date(j.date)} : ${j.alertes.length ? `${NIVEAUX[j.statut].libelle.toLowerCase()} (${j.alertes.join(", ")})` : "tous les contrôles OK"}`;
    $("historique").innerHTML = jours.map((j) => `<i class="n-${j.statut}" role="img" aria-label="${echapper(libelleJour(j))}" title="${echapper(libelleJour(j))}"></i>`).join("");
  }

  // --- Graphiques ---------------------------------------------------------------------------------------------------
  $("graphiques").hidden = false;
  const complets = new Set(rapport.mois_complets);
  const mensuel = rapport.mensuel.filter(([m]) => complets.has(m));
  const libelleMois = (m) => `${MOIS[Number(m.slice(5)) - 1]} ${m.slice(0, 4)}`;

  function graduations(max) {
    const brut = max / 4;
    const puissance = 10 ** Math.floor(Math.log10(brut || 1));
    const pas = [1, 2, 2.5, 5, 10].map((m) => m * puissance).find((p) => p >= brut);
    const ticks = [];
    for (let v = 0; v <= max + 1e-9; v += pas) ticks.push(v);
    if (ticks.at(-1) < max) ticks.push(ticks.at(-1) + pas);
    return ticks;
  }

  /** Courbes mensuelles sur un même axe, avec repère et info-bulle ; `series` : [{valeurs, classe}]. */
  function courbe(id, mois, series, format, bulle) {
    const conteneur = $(id);
    const l = Math.max(300, Math.round(conteneur.clientWidth || 600)), h = 220, g = 52, dr = 12, ha = 12, ba = 26;
    const ticks = graduations(Math.max(...series.flatMap((s) => s.valeurs), 1e-9));
    const ymax = ticks.at(-1);
    const n = mois.length;
    const x = (i) => g + (i * (l - g - dr)) / Math.max(n - 1, 1);
    const y = (v) => ha + (h - ha - ba) * (1 - v / ymax);
    let html = `<svg viewBox="0 0 ${l} ${h}" role="img" aria-label="${echapper(conteneur.closest("section").querySelector("h2").textContent)}"><g class="axe">`;
    for (const t of ticks) html += `<line x1="${g}" x2="${l - dr}" y1="${y(t)}" y2="${y(t)}"/><text x="${g - 8}" y="${y(t) + 4}" text-anchor="end">${format(t)}</text>`;
    mois.forEach((m, i) => {
      if (m.endsWith("-01")) html += `<text x="${x(i)}" y="${h - 6}" text-anchor="${i ? "middle" : "start"}">${m.slice(0, 4)}</text>`;
    });
    html += "</g>";
    for (const s of series) html += `<path class="ligne-serie ${s.classe ?? ""}" d="M${s.valeurs.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("L")}"/>`;
    html += `<g class="repere" hidden><line y1="${ha}" y2="${h - ba}"/>${series.map((s) => `<circle r="4" class="${s.classe ?? ""}"/>`).join("")}</g>`;
    html += `<rect x="${g}" y="0" width="${l - g - dr}" height="${h}" fill="transparent" class="zone"/></svg>`;
    conteneur.innerHTML = html;
    const svg = conteneur.querySelector("svg");
    const repere = svg.querySelector(".repere");
    svg.querySelector(".zone").addEventListener("pointermove", (e) => {
      const r = svg.getBoundingClientRect();
      const px = ((e.clientX - r.left) * l) / r.width;
      const i = Math.max(0, Math.min(n - 1, Math.round(((px - g) * (n - 1)) / (l - g - dr))));
      repere.hidden = false;
      for (const a of ["x1", "x2"]) repere.querySelector("line").setAttribute(a, x(i));
      repere.querySelectorAll("circle").forEach((c, k) => { c.setAttribute("cx", x(i)); c.setAttribute("cy", y(series[k].valeurs[i])); });
      montrerBulle(e, `${libelleMois(mois[i])}<br>${bulle(i)}`);
    });
    svg.querySelector(".zone").addEventListener("pointerleave", () => { repere.hidden = true; cacherBulle(); });
  }

  function graphiques() {
    const mois = mensuel.map(([m]) => m);
    courbe("g-offres", mois, [{ valeurs: mensuel.map(([, n]) => n) }], (v) => nombre(v), (i) => `<b>${nombre(mensuel[i][1])}</b> offres`);
    courbe("g-textes", mois, [{ valeurs: mensuel.map(([, n, t]) => t / n) }], (v) => pourcent(v, v < 0.1 ? 1 : 0),
      (i) => `<b>${pourcent(mensuel[i][2] / mensuel[i][1], 1)}</b> des offres<br>${nombre(mensuel[i][2])} textes sur ${nombre(mensuel[i][1])}`);
    const td = rapport.textes_defense;
    courbe("g-auteurs", td.map(([m]) => m), [{ valeurs: td.map(([, t, d]) => t - d), classe: "autres" }, { valeurs: td.map(([, , d]) => d), classe: "defense" }],
      (v) => nombre(v),
      (i) => `armées : <b>${nombre(td[i][2])}</b> textes pour ${nombre(td[i][3])} offres<br>autres employeurs : <b>${nombre(td[i][1] - td[i][2])}</b> textes`);
    const nouv = rapport.nouveautes;
    courbe("g-nouveautes", nouv.map(([m]) => m), [{ valeurs: nouv.map(([, n, k]) => k / n) }], (v) => pourcent(v),
      (i) => `<b>${pourcent(nouv[i][2] / nouv[i][1])}</b> de formes nouvelles<br>${nombre(nouv[i][2])} items sur ${nombre(nouv[i][1])}`);
  }
  graphiques();
  let largeur = innerWidth;
  addEventListener("resize", () => { if (innerWidth !== largeur) { largeur = innerWidth; graphiques(); } });

  // --- Employeurs et dérive -----------------------------------------------------------------------------------------
  const d = rapport.derive;
  const jour = (iso) => date(iso, { day: "numeric", month: "short", year: "numeric" });
  const recente = `six derniers mois du fichier (${jour(d.periode_recente[0])} – ${jour(d.periode_recente[1])})`;
  const avant = `deux années précédentes (${jour(d.periode_avant[0])} – ${jour(d.periode_avant[1])})`;
  $("employeurs-titre").textContent = `Part des annonces avec un texte écrites par chaque employeur : ${avant}, ${nombre(d.annonces.avant)} annonces, puis ${recente}, ${nombre(d.annonces.recente)} annonces.`;
  const max = Math.max(...d.employeurs_principaux.flatMap((e) => [e.part_avant, e.part_recente]), 1e-9);
  $("employeurs").innerHTML = d.employeurs_principaux.map((e) => `
    <div class="paire">
      <span class="nom" title="${echapper(e.organisme)}">${echapper(e.organisme)}</span>
      <span class="pistes" aria-hidden="true">
        <span class="piste"><span class="avant" style="width:${(100 * e.part_avant) / max}%"></span></span>
        <span class="piste"><span class="recente" style="width:${(100 * e.part_recente) / max}%"></span></span>
      </span>
      <span class="valeurs">avant ${pourcent(e.part_avant, 1)}<br>récent ${pourcent(e.part_recente, 1)}</span>
    </div>`).join("");
  const auteurs = controle.contributeurs;
  const composition = auteurs?.niveau === "alerte";
  $("employeurs-note").textContent = composition
    ? `Contrôle « auteurs de textes » : ${auteurs.detail}. Les chiffres bruts de compétences bougent alors sans que la demande ait changé, d'où la comparaison à employeurs constants ci-dessous.`
    : "Les chiffres bruts dépendent de qui écrit les textes : la comparaison à employeurs constants ci-dessous neutralise ces changements d'auteurs.";

  $("derive-titre").textContent = `Les ${recente} comparés aux ${avant}. Compétences du ROME citées par au moins 5 employeurs sur la période récente.`;
  const ec = d.employeurs_constants;
  const points = (v) => `${v > 0 ? "+" : ""}${nombre(100 * v, 1)}`;
  const intervalle = (c) => (c.ic === null ? "–" : `${points(c.ecart_constant - c.ic)} à ${points(c.ecart_constant + c.ic)}`);
  $("constants-note").textContent = `${nombre(ec.nombre)} employeurs présents dans les deux périodes (${nombre(ec.annonces_avant)} puis ${nombre(ec.annonces_recente)} annonces). Écart moyen, en points, de la part de leurs annonces qui citent la compétence, avec son intervalle de confiance à 95 %. q : probabilité corrigée de signaler une hausse qui n'en est pas une ; une hausse est retenue sous ${pourcent(d.seuil_fdr)}.`;
  const premiere = d.hausses_brutes[0];
  const comparaison = premiere
    ? ` Pour la plus forte hausse brute, « ${echapper(premiere.libelle)} », l'écart à employeurs constants est de ${points(premiere.ecart_constant)} point (intervalle ${intervalle(premiere)}), contre ${points(premiere.part_recente - premiere.part_avant)} en brut.`
    : "";
  if (ec.nombre < 30) {
    $("verdict").innerHTML = `<b>Trop peu d'employeurs présents dans les deux périodes (${nombre(ec.nombre)}) pour tester les hausses à employeurs constants.</b>`;
  } else if (d.significatives.length) {
    $("verdict").innerHTML = `<b>${d.significatives.length} ${d.significatives.length > 1 ? "compétences progressent" : "compétence progresse"} à employeurs constants</b> après correction pour ${nombre(d.competences_testees)} tests : ${d.significatives.slice(0, 5).map((s) => echapper(s.libelle)).join(", ")}.${comparaison}`;
  } else {
    $("verdict").innerHTML = `<b>Aucune hausse ne résiste à la correction pour ${nombre(d.competences_testees)} tests</b> à employeurs constants.${comparaison}` +
      (composition ? " Les hausses brutes tiennent surtout au changement d'auteurs des textes." : "") +
      " Avec ce nombre d'employeurs, seuls des écarts de plusieurs points seraient détectables.";
  }
  $("brutes").innerHTML = "<thead><tr><th>Compétence</th><th>Avant</th><th>Récent</th><th>Premier employeur</th><th>À employeurs constants</th></tr></thead><tbody>" +
    d.hausses_brutes.slice(0, 10).map((c) => `<tr><td>${echapper(c.libelle)}</td><td>${pourcent(c.part_avant, 1)}</td><td>${pourcent(c.part_recente, 1)}</td><td>${pourcent(c.concentration)}</td><td>${points(c.ecart_constant)}</td></tr>`).join("") + "</tbody>";
  $("constantes").innerHTML = "<thead><tr><th>Compétence</th><th>Écart</th><th>Intervalle à 95 %</th><th>q</th></tr></thead><tbody>" +
    d.hausses_constantes.slice(0, 10).map((c) => `<tr><td>${echapper(c.libelle)}</td><td>${points(c.ecart_constant)}</td><td>${intervalle(c)}</td><td>${c.q === null ? "–" : nombre(c.q, 2)}</td></tr>`).join("") + "</tbody>";
})();
