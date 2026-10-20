// Outil « Mes compétences » : envoie le texte au travail de fond (js/outil-worker.js) et affiche les compétences
// repérées, leur répartition par domaine et les fiches métier les plus proches.

(function () {
  const { nombre, echapper } = Commun;
  const $ = (id) => document.getElementById(id);

  const EXEMPLE = `Chargé·e d'études statistiques

Missions : produire et analyser des indicateurs sur l'activité des services, réaliser des enquêtes, valoriser les résultats auprès des décideurs.

Compétences attendues :
- Maîtrise des méthodes statistiques et de l'analyse de données
- Programmation en R ou Python, SQL
- Conception et exploitation d'enquêtes
- Datavisualisation
- Capacités rédactionnelles
- Connaissance de l'environnement administratif
Savoir-être : rigueur, autonomie, esprit d'équipe, curiosité`;

  const travail = new Worker("js/outil-worker.js", { type: "module" });
  let demande = 0;
  travail.onmessage = ({ data }) => {
    if (data.type === "pret") {
      $("extraire").disabled = false;
      $("extraire").textContent = "Extraire les compétences";
      $("etat").textContent = `Référentiel prêt : ${nombre(data.competences)} compétences et savoirs du ROME.`;
      $("nb-formes").textContent = nombre(data.formes);
      $("nb-fiches").textContent = nombre(data.fiches);
      return;
    }
    if (data.type === "erreur") {
      $("etat").textContent = `Erreur : ${data.message}`;
      $("extraire").disabled = false;
      return;
    }
    if (data.id === demande) afficher(data);
  };
  travail.onerror = (e) => { $("etat").textContent = `Le navigateur n'a pas pu lancer l'outil (${e.message ?? "erreur"}).`; };
  travail.postMessage({ type: "pret" });

  $("exemple").addEventListener("click", () => {
    $("texte").value = EXEMPLE;
    if (!$("extraire").disabled) $("formulaire").requestSubmit();
  });
  $("formulaire").addEventListener("submit", (e) => {
    e.preventDefault();
    const texte = $("texte").value.trim();
    if (!texte) return;
    demande += 1;
    $("etat").textContent = "Analyse…";
    travail.postMessage({ type: "texte", id: demande, texte });
  });

  const BADGES = {
    vue: (r) => [`vue ${nombre(r.occurrences)} fois dans les offres`, "vue"],
    proche: () => ["rapprochement proche", "proche"],
    approximatif: () => ["rapprochement approximatif", "approx"],
    incertain: () => ["incertain", "incertain"],
  };
  const badge = (r) => {
    const [texte, classe] = BADGES[r.source === "vue" ? "vue" : r.niveau](r);
    const titre = r.source === "tfidf" ? ` title="similarité TF-IDF ${nombre(r.score, 2)}"` : "";
    return `<span class="badge ${classe}"${titre}>${texte}</span>` +
      (r.transversale ? '<span class="badge transversale" title="citée par au moins 5 % des annonces : ne compte pas pour les fiches métier">transversale</span>' : "");
  };
  const ligne = (r) => `<div class="item"><div class="source">${echapper(r.item)}</div>` +
    `<div class="cible">${r.libelle ? `<b>${echapper(r.libelle)}</b><small>${echapper(r.domaine)}${r.macro ? ` · ${echapper(r.macro)}` : ""}</small>` : "<small>aucune correspondance</small>"}${badge(r)}</div></div>`;

  function afficher({ resultats, fiches }) {
    $("resultats").hidden = false;
    const fiables = resultats.filter((r) => r.entree !== null && r.niveau !== "incertain");
    const incertains = resultats.filter((r) => !fiables.includes(r));
    const distinctes = new Set(fiables.map((r) => r.entree)).size;
    $("etat").textContent = "";
    $("bilan").textContent = resultats.length
      ? `${nombre(resultats.length)} items repérés, ${nombre(fiables.length)} rattachés au ROME (${nombre(distinctes)} compétences distinctes).`
      : "Aucun item repéré : le texte est-il découpé en lignes ou en listes ?";
    $("items").innerHTML = fiables.map(ligne).join("") || '<p class="discret petit">Aucun rattachement fiable.</p>';
    $("details-incertains").hidden = !incertains.length;
    $("resume-incertains").textContent = `${nombre(incertains.length)} ${incertains.length > 1 ? "items" : "item"} sans correspondance fiable`;
    $("incertains").innerHTML = incertains.map(ligne).join("");

    const parDomaine = new Map();
    for (const r of fiables) parDomaine.set(r.domaine, (parDomaine.get(r.domaine) ?? 0) + 1);
    const domaines = [...parDomaine].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    const max = domaines[0]?.[1] ?? 1;
    $("domaines").innerHTML = domaines.map(([d, n]) =>
      `<div class="barre"><span class="nom" title="${echapper(d)}">${echapper(d)}</span><span class="piste"><span class="remplissage" style="width:${(100 * n) / max}%"></span></span><span class="valeur">${n}</span></div>`).join("")
      || '<p class="discret petit">–</p>';

    $("fiches").innerHTML = fiches.length ? fiches.map((f, i) => `
      <article class="fiche">
        <h3><span class="fiche-code">${f.code}</span><a href="https://candidat.francetravail.fr/metierscope/fiche-metier/${f.code}" target="_blank" rel="noopener">${echapper(f.libelle)}</a></h3>
        <p class="petit discret">${nombre(f.communes.length)} compétences en commun : ${f.communes.slice(0, 4).map(echapper).join(" ; ")}${f.communes.length > 4 ? "…" : ""}</p>
        ${f.metiers.length ? `<p class="petit">Dans la fonction publique : ${f.metiers.map(([id, m]) => `<a href="tableau.html#m=${id}">${echapper(m)}</a>`).join(", ")}</p>` : ""}
        ${i === 0 && f.manquantes.length ? `<details class="manquantes"><summary>Compétences du cœur de métier absentes du texte</summary><ul>${f.manquantes.map((m) => `<li>${echapper(m)}</li>`).join("")}</ul></details>` : ""}
      </article>`).join("")
      : '<p class="discret petit">Trop peu de compétences rattachées pour comparer aux fiches métier.</p>';
    $("resultats").scrollIntoView({ behavior: "smooth", block: "start" });
  }
})();
