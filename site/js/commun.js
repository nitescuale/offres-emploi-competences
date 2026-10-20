// Outils partagés par les pages : chargement des données, formats français, info-bulle, échappement HTML.

const Commun = (() => {
  const cache = {};

  /** Charge un fichier JSON du site (chemin relatif, sans l'extension), une seule fois. */
  function charger(chemin) {
    cache[chemin] ??= fetch(`${chemin}.json`).then((reponse) => {
      if (!reponse.ok) throw new Error(`${chemin}.json : ${reponse.status}`);
      return reponse.json();
    });
    return cache[chemin];
  }

  /** {colonnes, lignes} → liste d'objets. */
  function objets(table) {
    const { colonnes, lignes } = table;
    return lignes.map((ligne) => Object.fromEntries(colonnes.map((c, i) => [c, ligne[i]])));
  }

  const formats = {};
  function nombre(valeur, decimales = 0) {
    if (valeur === null || valeur === undefined || Number.isNaN(valeur)) return "–";
    formats[decimales] ??= new Intl.NumberFormat("fr-FR", { minimumFractionDigits: decimales, maximumFractionDigits: decimales });
    return formats[decimales].format(valeur).replace("-", "−");
  }
  /** Part (0-1) en pourcentage ; « – » quand le dénominateur est nul. */
  const pourcent = (part, decimales = 0) => (part === null || !Number.isFinite(part) ? "–" : `${nombre(100 * part, decimales)} %`);

  const MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
  function date(iso, options = { day: "numeric", month: "long", year: "numeric" }) {
    if (!iso) return "–";
    return new Date(`${iso}T12:00:00`).toLocaleDateString("fr-FR", options);
  }

  const echapper = (texte) =>
    String(texte ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  /** Une seule info-bulle par page, placée près du pointeur sans sortir de l'écran. */
  let bulle;
  function montrerBulle(evenement, html) {
    bulle ??= Object.assign(document.body.appendChild(document.createElement("div")), { className: "bulle", role: "tooltip" });
    bulle.innerHTML = html;
    bulle.hidden = false;
    const { innerWidth: l, innerHeight: h } = window;
    const r = bulle.getBoundingClientRect();
    let x = evenement.clientX + 14;
    let y = evenement.clientY + 14;
    if (x + r.width > l - 8) x = evenement.clientX - r.width - 14;
    if (y + r.height > h - 8) y = evenement.clientY - r.height - 14;
    bulle.style.left = `${Math.max(8, x)}px`;
    bulle.style.top = `${Math.max(8, y)}px`;
  }
  const cacherBulle = () => bulle && (bulle.hidden = true);

  return { charger, objets, nombre, pourcent, date, MOIS, echapper, montrerBulle, cacherBulle };
})();
