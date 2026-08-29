"""
MAC Bot - Calcul des pips, détection des swings, et gestion stricte du risque

RÈGLE NON-NÉGOCIABLE : le ratio Risque:Récompense de chaque position envoyée doit
être compris STRICTEMENT entre 1.50 et 3.50. En dehors, le signal n'est jamais
envoyé, peu importe la qualité apparente du setup.

CALCUL DES PIPS (identique à MR EMA) :
- Forex classique : 1 pip = 0.0001
- Paires JPY : 1 pip = 0.01
- Métaux (XAU/XAG) : 1 pip = 0.01 (convention de marché)
- Crypto : pas de pip au sens Forex, mouvement exprimé directement en USD
"""

from dataclasses import dataclass
from typing import Optional
import pandas as pd
import config


def valeur_pip(asset_type: str, symbol: str) -> float:
    if asset_type == "crypto":
        return 1.0
    if asset_type == "metal":
        return 0.01
    if asset_type == "forex":
        if "JPY" in symbol.upper():
            return 0.01
        return 0.0001
    raise ValueError(f"Type d'actif inconnu: {asset_type}")


def calculer_pips(prix_entree: float, prix_sortie: float, asset_type: str, symbol: str) -> float:
    pip_val = valeur_pip(asset_type, symbol)
    diff = prix_sortie - prix_entree
    if asset_type == "crypto":
        return round(diff, 2)
    return round(diff / pip_val, 1)


def trouver_swing_high(df: pd.DataFrame, fenetre: int, exclure_derniere_n: int = 1) -> Optional[float]:
    """
    Trouve le plus haut local le plus récent dans les `fenetre` dernières bougies,
    en excluant les `exclure_derniere_n` bougies les plus récentes (typiquement la
    bougie d'entrée elle-même, pour ne pas prendre son propre plus haut comme cible).
    """
    if len(df) < fenetre + exclure_derniere_n:
        return None
    zone = df["High"].iloc[-(fenetre + exclure_derniere_n):-exclure_derniere_n] if exclure_derniere_n > 0 else df["High"].iloc[-fenetre:]
    if zone.empty:
        return None
    return float(zone.max())


def trouver_swing_low(df: pd.DataFrame, fenetre: int, exclure_derniere_n: int = 1) -> Optional[float]:
    """Symétrique de trouver_swing_high, pour les positions de vente."""
    if len(df) < fenetre + exclure_derniere_n:
        return None
    zone = df["Low"].iloc[-(fenetre + exclure_derniere_n):-exclure_derniere_n] if exclure_derniere_n > 0 else df["Low"].iloc[-fenetre:]
    if zone.empty:
        return None
    return float(zone.min())


@dataclass
class NiveauxPosition:
    direction: str
    prix_entree: float
    stop_loss: float
    take_profit: float
    ratio_rr: float
    pips_risque: float
    pips_recompense: float


def construire_niveaux(direction: str, prix_entree: float, stop_loss_propose: float,
                        take_profit_propose: float, asset_type: str, symbol: str) -> Optional[NiveauxPosition]:
    """
    Construit et VALIDE les niveaux d'une position à partir d'une entrée, d'un SL et
    d'un TP déjà déterminés par la stratégie (retest EMA50, ou croisement+rejection).

    Retourne None si le ratio RR résultant est hors de l'intervalle [1.50, 3.50] -
    dans ce cas, AUCUN signal ne doit être envoyé, quelle que soit la qualité du setup.
    """
    if direction == "ACHAT":
        distance_risque = prix_entree - stop_loss_propose
        distance_recompense = take_profit_propose - prix_entree
    elif direction == "VENTE":
        distance_risque = stop_loss_propose - prix_entree
        distance_recompense = prix_entree - take_profit_propose
    else:
        raise ValueError(f"Direction invalide: {direction}")

    # Le risque et la récompense doivent être des distances positives et non nulles -
    # une distance négative ou nulle indique un SL/TP mal positionné (ex: TP du mauvais
    # côté du prix d'entrée), donc le signal est invalide dans tous les cas.
    if distance_risque <= 0 or distance_recompense <= 0:
        return None

    ratio_rr = round(distance_recompense / distance_risque, 2)

    if not (config.MIN_RISK_REWARD <= ratio_rr <= config.MAX_RISK_REWARD):
        return None

    pips_risque = abs(calculer_pips(prix_entree, stop_loss_propose, asset_type, symbol))
    pips_recompense = abs(calculer_pips(prix_entree, take_profit_propose, asset_type, symbol))

    return NiveauxPosition(
        direction=direction,
        prix_entree=round(prix_entree, 5),
        stop_loss=round(stop_loss_propose, 5),
        take_profit=round(take_profit_propose, 5),
        ratio_rr=ratio_rr,
        pips_risque=pips_risque,
        pips_recompense=pips_recompense,
    )
