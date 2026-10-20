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
    `<span class="statut ${niveau}"><span class="icone" aria-hidden="true">${NIVEAUX[niveau].icone}</span>${texte ?? NIVEAUX[niveau].libelle}</span>`;

  // --- Chaîne de traitements ---------------------------------------------------------------------------------------
  const CHAINE = [
    ["csp.yml", "Offres Choisir le service public", "Chaque lundi : les fichiers annuels de data.gouv.fr, normalisés en un seul Parquet. Refuse de publier un fichier amputé."],
    ["competences.yml", "Compétences", "Après chaque mise à jour des offres : textes découpés, items rattachés au ROME (seules les formes nouvelles sont calculées)."],
    ["suivi.yml", "Suivi", "Chaque jour et après les compétences : les contrôles et la dérive présentés sur cette page."],
    ["site.yml", "Site", "Après chaque suivi : données du tableau de bord et de l'outil recalculées, site publié."],
    ["collecte.yml", "Collecte France Travail", "Chaque jour : prête, en attente d'un accès à l'API Offres d'emploi, devenue restreinte."],
    ["ci.yml", "Tests", "À chaque modification du code : tests, dont la parité du JavaScript de l'outil avec le Python."],
  ];
  $("chaine").innerHTML = CHAINE.map(([fichier, nom, texte]) => `
    <li>
      <div><b>${nom}</b><p class="petit discret">${texte}</p></div>
      <a class="passage" id="w-${fichier.replace(".yml", "")}" href="https://github.com/${DEPOT}/actions/workflows/${fichier}">…</a>
    </li>`).join("");
  const heure = (iso) => new Date(iso).toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  for (const [fichier] of CHAINE) {
    const lien = $(`w-${fichier.replace(".yml", "")}`);
    fetch(`https://api.github.com/repos/${DEPOT}/actions/workflows/${fichier}/runs?per_page=1&exclude_pull_requests=true`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(({ workflow_runs: [run] }) => {
        if (!run) { lien.textContent = "pas encore lancé"; return; }
        lien.href = run.html_url;
        if (run.status !== "completed") { lien.innerHTML = `<span class="statut cours">en cours</span>`; return; }
        const niveau = run.conclusion === "success" ? "ok" : run.conclusion === "failure" ? "erreur" : "alerte";
        const mot = { success: "réussi", failure: "échoué", cancelled: "annulé", skipped: "ignoré" }[run.conclusion] ?? run.conclusion;
        lien.innerHTML = `${pastille(niveau, mot)}<small>${heure(run.updated_at)}</small>`;
      })
      .catch(() => { lien.textContent = "voir sur GitHub"; });
  }

  // --- Rapports du suivi --------------------------------------------------------------------------------------------
  let rapport, historique;
  try {
    [rapport, historique] = await Promise.all([charger("donnees/suivi_dernier"), charger("donnees/suivi_historique")]);
  } catch {
    $("sans-controle").hidden = false;
    $("controles-date").textContent = "Chaque jour, sur les fichiers publiés.";
    return;
  }

  $("statut-global").outerHTML = pastille(rapport.statut);
  const maj = rapport.source?.mise_a_jour_fichier ? ` · fichier de l'année mis à jour le ${date(rapport.source.mise_a_jour_fichier)}` : "";
  $("controles-date").textContent = `Contrôle du ${date(rapport.date)} · ${nombre(rapport.offres)} offres, la dernière publiée le ${date(rapport.derniere_publication)}${maj}`;
  const ordre = { erreur: 0, alerte: 1, ok: 2 };
  $("controles").innerHTML = "<thead><tr><th>Contrôle</th><th>État</th><th>Détail</th></tr></thead><tbody>" +
    [...rapport.controles].sort((a, b) => ordre[a.niveau] - ordre[b.niveau]).map((c) =>
      `<tr><td>${echapper(c.libelle)}</td><td>${pastille(c.niveau)}</td><td class="discret">${echapper(c.detail)}</td></tr>`).join("") +
    "</tbody>";

  const jours = historique.slice(-90);
  if (jours.length > 1) {
    $("historique-bloc").hidden = false;
    const nb = (n) => jours.filter((j) => j.statut === n).length;
    $("historique-titre").textContent = `${jours.length} derniers contrôles : ${nb("ok")} sans alerte, ${nb("alerte")} avec alerte, ${nb("erreur")} en erreur.`;
    $("historique").innerHTML = jours.map((j) => `<i class="${j.statut}" data-date="${j.date}" data-alertes="${echapper(j.alertes.join(", "))}"></i>`).join("");
    $("historique").addEventListener("pointermove", (e) => {
      const j = e.target.closest("i");
      if (!j) return cacherBulle();
      montrerBulle(e, `${date(j.dataset.date)}<br>${j.dataset.alertes ? `à revoir : ${j.dataset.alertes}` : "tous les contrôles OK"}`);
    });
    $("historique").addEventListener("pointerleave", cacherBulle);
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

  /** Courbe mensuelle avec repère et info-bulle ; `format` écrit les valeurs (axe et bulle). */
  function courbe(id, mois, valeurs, format, bulle) {
    const conteneur = $(id);
    const l = Math.max(300, Math.round(conteneur.clientWidth || 600)), h = 220, g = 52, dr = 12, ha = 12, ba = 26;
    const ticks = graduations(Math.max(...valeurs, 1e-9));
    const ymax = ticks.at(-1);
    const x = (i) => g + (i * (l - g - dr)) / Math.max(valeurs.length - 1, 1);
    const y = (v) => ha + (h - ha - ba) * (1 - v / ymax);
    let html = `<svg viewBox="0 0 ${l} ${h}" role="img" aria-label="${echapper(conteneur.closest("section").querySelector("h2").textContent)}"><g class="axe">`;
    for (const t of ticks) html += `<line x1="${g}" x2="${l - dr}" y1="${y(t)}" y2="${y(t)}"/><text x="${g - 8}" y="${y(t) + 4}" text-anchor="end">${format(t)}</text>`;
    mois.forEach((m, i) => {
      if (m.endsWith("-01")) html += `<text x="${x(i)}" y="${h - 6}" text-anchor="${i ? "middle" : "start"}">${m.slice(0, 4)}</text>`;
    });
    html += "</g>";
    const pts = valeurs.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
    html += `<path class="ligne-serie" d="M${pts.join("L")}"/>`;
    html += `<g class="repere" hidden><line y1="${ha}" y2="${h - ba}"/><circle r="4"/></g>`;
    html += `<rect x="${g}" y="0" width="${l - g - dr}" height="${h}" fill="transparent" class="zone"/></svg>`;
    conteneur.innerHTML = html;
    const svg = conteneur.querySelector("svg");
    const repere = svg.querySelector(".repere");
    svg.querySelector(".zone").addEventListener("pointermove", (e) => {
      const r = svg.getBoundingClientRect();
      const px = ((e.clientX - r.left) * l) / r.width;
      const i = Math.max(0, Math.min(valeurs.length - 1, Math.round(((px - g) * (valeurs.length - 1)) / (l - g - dr))));
      repere.hidden = false;
      for (const a of ["x1", "x2"]) repere.querySelector("line").setAttribute(a, x(i));
      repere.querySelector("circle").setAttribute("cx", x(i));
      repere.querySelector("circle").setAttribute("cy", y(valeurs[i]));
      montrerBulle(e, `${libelleMois(mois[i])}<br>${bulle(i)}`);
    });
    svg.querySelector(".zone").addEventListener("pointerleave", () => { repere.hidden = true; cacherBulle(); });
  }

  function graphiques() {
    const mois = mensuel.map(([m]) => m);
    courbe("g-offres", mois, mensuel.map(([, n]) => n), (v) => nombre(v), (i) => `<b>${nombre(mensuel[i][1])}</b> offres`);
    courbe("g-textes", mois, mensuel.map(([, n, t]) => t / n), (v) => pourcent(v, v < 0.1 ? 1 : 0),
      (i) => `<b>${pourcent(mensuel[i][2] / mensuel[i][1], 1)}</b> des offres<br>${nombre(mensuel[i][2])} textes sur ${nombre(mensuel[i][1])}`);
    const nouv = rapport.nouveautes;
    courbe("g-nouveautes", nouv.map(([m]) => m), nouv.map(([, n, k]) => k / n), (v) => pourcent(v),
      (i) => `<b>${pourcent(nouv[i][2] / nouv[i][1])}</b> de formes nouvelles<br>${nombre(nouv[i][2])} items sur ${nombre(nouv[i][1])}`);
  }
  graphiques();
  let largeur = innerWidth;
  addEventListener("resize", () => { if (innerWidth !== largeur) { largeur = innerWidth; graphiques(); } });

  // --- Employeurs et dérive -----------------------------------------------------------------------------------------
  const d = rapport.derive;
  const periode = (p) => `${date(p[0], { month: "short", year: "numeric" })} à ${date(p[1], { month: "short", year: "numeric" })}`;
  $("employeurs-titre").textContent = `Part des annonces avec un texte, ${periode(d.periode_avant)} (${nombre(d.annonces.avant)} annonces) puis ${periode(d.periode_recente)} (${nombre(d.annonces.recente)}).`;
  const max = Math.max(...d.employeurs_principaux.flatMap((e) => [e.part_avant, e.part_recente]), 1e-9);
  $("employeurs").innerHTML = d.employeurs_principaux.map((e) => `
    <div class="paire">
      <span class="nom" title="${echapper(e.organisme)}">${echapper(e.organisme)}</span>
      <span class="pistes">
        <span class="piste"><span class="avant" style="width:${(100 * e.part_avant) / max}%"></span></span>
        <span class="piste"><span class="recente" style="width:${(100 * e.part_recente) / max}%"></span></span>
      </span>
      <span class="valeurs">${pourcent(e.part_avant, 1)}<br>${pourcent(e.part_recente, 1)}</span>
    </div>`).join("");
  const taris = d.employeurs_principaux.filter((e) => e.part_avant >= 0.02 && e.part_recente < e.part_avant / 4);
  $("employeurs-note").textContent = taris.length
    ? `${taris.length > 1 ? `${taris.length} de ces employeurs ont` : "Un de ces employeurs a"} presque cessé de remplir le champ « compétences » tout en continuant de publier des offres : les chiffres bruts de compétences bougent alors sans que la demande ait changé. C'est la raison de la comparaison à employeurs constants ci-dessous.`
    : "Aucun des principaux auteurs de textes n'a cessé d'en écrire.";

  $("derive-titre").textContent = `${periode(d.periode_recente)} comparés à ${periode(d.periode_avant)}, compétences du ROME citées par au moins 5 employeurs sur la période récente.`;
  const ec = d.employeurs_constants;
  $("constants-note").textContent = `${nombre(ec.nombre)} employeurs présents dans les deux périodes (${nombre(ec.annonces_avant)} puis ${nombre(ec.annonces_recente)} annonces). Écart moyen de la part de leurs annonces qui citent la compétence, en points.`;
  $("verdict").innerHTML = d.significatives.length
    ? `<b>${d.significatives.length} ${d.significatives.length > 1 ? "compétences progressent" : "compétence progresse"} à employeurs constants</b> après correction pour ${nombre(d.competences_testees)} tests : ${d.significatives.slice(0, 5).map((s) => echapper(s.libelle)).join(", ")}.`
    : `<b>Aucune compétence ne progresse nettement à employeurs constants</b> : sur ${nombre(d.competences_testees)} compétences testées, aucune ne passe le seuil après correction (taux de fausses découvertes de ${pourcent(d.seuil_fdr)}). Les hausses brutes viennent surtout du changement d'auteurs des textes.`;
  const points = (v) => `${v > 0 ? "+" : ""}${nombre(100 * v, 1)}`;
  $("brutes").innerHTML = "<thead><tr><th>Compétence</th><th>Avant</th><th>Récente</th><th>Premier employeur</th></tr></thead><tbody>" +
    d.hausses_brutes.slice(0, 10).map((c) => `<tr><td>${echapper(c.libelle)}</td><td>${pourcent(c.part_avant, 1)}</td><td>${pourcent(c.part_recente, 1)}</td><td>${pourcent(c.concentration)}</td></tr>`).join("") + "</tbody>";
  $("constantes").innerHTML = "<thead><tr><th>Compétence</th><th>Écart</th><th>t</th><th>q</th></tr></thead><tbody>" +
    d.hausses_constantes.slice(0, 10).map((c) => `<tr><td>${echapper(c.libelle)}</td><td>${points(c.ecart_constant)}</td><td>${nombre(c.t, 1)}</td><td>${c.q === null ? "–" : nombre(c.q, 2)}</td></tr>`).join("") + "</tbody>";
})();
