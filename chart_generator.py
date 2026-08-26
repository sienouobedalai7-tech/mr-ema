"""
MR EMA - Génération de graphiques

Génère une image PNG du graphique réel (bougies + EMA50/200 + niveaux SL/TP) à partir
des données Yahoo Finance récupérées pour l'analyse. Ce n'est pas une image de synthèse
ou un placeholder : c'est le graphique tracé directement à partir des mêmes bougies que
celles utilisées pour la décision de trading, avec les mêmes limites de fraîcheur des
données (~15-20 min de délai Yahoo Finance) mentionnées ailleurs dans le projet.
"""

import matplotlib
matplotlib.use("Agg")  # backend sans interface graphique, nécessaire pour tourner en cron/CI
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd


def generer_graphique(df_entry_avec_indicateurs: pd.DataFrame, ticker_display: str,
                       direction: str, prix_entree: float, stop_loss: float,
                       take_profits: list, chemin_sortie: str, nb_bougies_affichees: int = 100) -> str:
    """
    Génère un graphique en chandeliers avec EMA50/200 et niveaux SL/TP superposés.

    Args:
        df_entry_avec_indicateurs: DataFrame M15 avec colonnes OHLC + ema_fast + ema_slow
        ticker_display: nom affiché (ex: "XAU/USD (Or)")
        direction: "ACHAT" ou "VENTE"
        prix_entree, stop_loss: niveaux à tracer
        take_profits: liste des TP à tracer (1 à 3 valeurs)
        chemin_sortie: chemin du fichier PNG à créer
        nb_bougies_affichees: nombre de bougies récentes à afficher (zoom sur l'action récente)

    Returns:
        Le chemin du fichier généré
    """
    data = df_entry_avec_indicateurs.tail(nb_bougies_affichees).copy()

    fig, ax = plt.subplots(figsize=(12, 7))

    # --- Chandeliers dessinés manuellement (pas de dépendance mplfinance pour rester léger) ---
    largeur_bougie = 0.6
    for i, (idx, row) in enumerate(data.iterrows()):
        couleur = "#26a69a" if row["Close"] >= row["Open"] else "#ef5350"
        # mèche haute/basse
        ax.plot([i, i], [row["Low"], row["High"]], color=couleur, linewidth=1, zorder=2)
        # corps de la bougie
        bas_corps = min(row["Open"], row["Close"])
        hauteur_corps = abs(row["Close"] - row["Open"])
        if hauteur_corps == 0:
            hauteur_corps = (row["High"] - row["Low"]) * 0.01  # évite un corps invisible sur un doji
        ax.add_patch(plt.Rectangle((i - largeur_bougie / 2, bas_corps), largeur_bougie, hauteur_corps,
                                     facecolor=couleur, edgecolor=couleur, zorder=3))

    # --- EMA 50 / 200 ---
    x_vals = range(len(data))
    if "ema_fast" in data.columns:
        ax.plot(x_vals, data["ema_fast"], color="#2196F3", linewidth=1.3, label="EMA 50", zorder=4)
    if "ema_slow" in data.columns:
        ax.plot(x_vals, data["ema_slow"], color="#FF9800", linewidth=1.3, label="EMA 200", zorder=4)

    # --- Niveaux d'entrée / SL / TP ---
    ax.axhline(prix_entree, color="#FFFFFF", linestyle="-", linewidth=1.2,
               label=f"Entrée: {prix_entree:.5f}", zorder=5)
    ax.axhline(stop_loss, color="#e53935", linestyle="--", linewidth=1.2,
               label=f"SL: {stop_loss:.5f}", zorder=5)

    couleurs_tp = ["#43a047", "#66bb6a", "#a5d6a7"]
    for i, tp in enumerate(take_profits):
        if tp is not None:
            ax.axhline(tp, color=couleurs_tp[i % len(couleurs_tp)], linestyle="--", linewidth=1.2,
                       label=f"TP{i+1}: {tp:.5f}", zorder=5)

    # --- Habillage ---
    # Pas d'emoji dans le titre matplotlib : la police par défaut (DejaVu Sans) ne les
    # supporte pas et les affiche comme des carrés vides. Les emojis restent dans le
    # message Telegram qui l'accompagne, où ils s'affichent nativement.
    couleur_direction = "#26a69a" if direction == "ACHAT" else "#ef5350"
    ax.set_title(f"MR EMA — {ticker_display} — {direction}", fontsize=14, fontweight="bold", color=couleur_direction)
    ax.set_xlabel("Bougies M15 (données Yahoo Finance, différé ~15-20 min)", fontsize=9, color="#bbbbbb")
    ax.legend(loc="best", fontsize=8, framealpha=0.85)
    ax.set_xlim(-1, len(data))

    # Thème sombre (plus lisible sur Telegram mobile)
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
