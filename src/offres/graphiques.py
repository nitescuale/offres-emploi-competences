"""Style commun des figures : traits fins, grille discrète, palette catégorielle validée (daltonisme compris)."""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt

# Ordre fixe, jamais recyclé : bleu, orange, aqua (les trois premiers passent tous les contrôles deux à deux)
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
GRIS = "#8a8984"
SEQUENTIEL = "Blues"
VERSANTS = {
    "Fonction Publique Territoriale": PALETTE[0],
    "Fonction Publique de l'Etat": PALETTE[1],
    "Fonction Publique Hospitalière": PALETTE[2],
}
FIGURES = Path(__file__).resolve().parents[2] / "rapports" / "figures"


def style() -> None:
    mpl.rcParams.update({
        "figure.figsize": (9, 4.5), "figure.dpi": 110, "savefig.dpi": 150, "savefig.bbox": "tight",
        "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#b5b4ae",
        "axes.grid": True, "grid.color": "#e6e5e0", "grid.linewidth": 0.6, "axes.axisbelow": True,
        "axes.prop_cycle": mpl.cycler(color=PALETTE), "lines.linewidth": 2,
        "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "font.size": 10, "legend.frameon": False, "xtick.color": "#52514e", "ytick.color": "#52514e",
    })


def enregistrer(fig: plt.Figure, nom: str) -> Path:
    FIGURES.mkdir(parents=True, exist_ok=True)
    chemin = FIGURES / f"{nom}.png"
    fig.savefig(chemin)
    return chemin
