"""
MAC Bot - Génération de graphiques

Génère une image PNG à partir des mêmes bougies Twelve Data utilisées pour la
décision de trading, avec EMA50/EMA200 et niveaux Entrée/SL/TP superposés.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def generer_graphique(df_ind: pd.DataFrame, display: str, direction: str, prix_entree: float,
                       stop_loss: float, take_profit: float, chemin_sortie: str,
                       nb_bougies_affichees: int = 100) -> str:
    data = df_ind.tail(nb_bougies_affichees).copy()

    fig, ax = plt.subplots(figsize=(12, 7))

    largeur_bougie = 0.6
    for i, (idx, row) in enumerate(data.iterrows()):
        couleur = "#26a69a" if row["Close"] >= row["Open"] else "#ef5350"
        ax.plot([i, i], [row["Low"], row["High"]], color=couleur, linewidth=1, zorder=2)
        bas_corps = min(row["Open"], row["Close"])
        hauteur_corps = abs(row["Close"] - row["Open"])
        if hauteur_corps == 0:
            hauteur_corps = (row["High"] - row["Low"]) * 0.01
        ax.add_patch(plt.Rectangle((i - largeur_bougie / 2, bas_corps), largeur_bougie, hauteur_corps,
                                     facecolor=couleur, edgecolor=couleur, zorder=3))

    x_vals = range(len(data))
    if "ema_fast" in data.columns:
        ax.plot(x_vals, data["ema_fast"], color="#2196F3", linewidth=1.3, label="EMA 50", zorder=4)
    if "ema_slow" in data.columns:
        ax.plot(x_vals, data["ema_slow"], color="#FF9800", linewidth=1.3, label="EMA 200", zorder=4)

    ax.axhline(prix_entree, color="#FFFFFF", linestyle="-", linewidth=1.2,
               label=f"Entrée: {prix_entree:.5f}", zorder=5)
    ax.axhline(stop_loss, color="#e53935", linestyle="--", linewidth=1.2,
               label=f"SL: {stop_loss:.5f}", zorder=5)
    ax.axhline(take_profit, color="#43a047", linestyle="--", linewidth=1.2,
               label=f"TP: {take_profit:.5f}", zorder=5)

    couleur_direction = "#26a69a" if direction == "ACHAT" else "#ef5350"
    ax.set_title(f"MAC Bot — {display} — {direction}", fontsize=14, fontweight="bold", color=couleur_direction)
    ax.set_xlabel("Bougies M15 (Twelve Data, délai variable selon le marché)", fontsize=9, color="#bbbbbb")
    ax.legend(loc="best", fontsize=8, framealpha=0.85)
    ax.set_xlim(-1, len(data))

    fig.patch.set_facecolor("#131722")
    ax.set_facecolor("#131722")
    ax.tick_params(colors="#bbbbbb")
    for spine in ax.spines.values():
        spine.set_color("#363c4e")
    ax.grid(True, color="#242832", linewidth=0.5)

    plt.tight_layout()
    plt.savefig(chemin_sortie, dpi=130, facecolor=fig.get_facecolor())
    plt.close(fig)

    return chemin_sortie
