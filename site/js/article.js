// Le bandeau « Les données » de l'article : chiffres tirés de donnees/resume.json, mis à jour à chaque construction.

(async function () {
  const { nombre, date } = Commun;
  let resume;
  try {
    resume = await Commun.charger("donnees/resume");
  } catch {
    return; // les chiffres écrits dans la page restent affichés
  }
  const ecrire = (cle, texte) => {
    const element = document.querySelector(`[data-chiffre="${cle}"]`);
    if (element) element.textContent = texte;
  };
  ecrire("offres", nombre(resume.offres));
  ecrire("metiers", nombre(resume.metiers));
  ecrire("textes", nombre(resume.textes));
  document.getElementById("maj").textContent = `offres publiées jusqu'au ${date(resume.fin)} · mis à jour le ${date(resume.mise_a_jour)}`;
})();
