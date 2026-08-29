"""
MAC Bot - Logique des 2 stratégies BTMM

STRATÉGIE 1 - Retest EMA50 + confirmation TDI :
  1. Tendance déterminée par EMA50 vs EMA200 (écart suffisant pour éviter le range)
  2. Le prix revient tester l'EMA50 (contact, pas forcément un croisement exact)
  3. Confirmation : le RSI (composante du TDI) rebondit sur sa ligne médiane (50)
     au même moment que le test du prix sur l'EMA50
  4. TP = prochain swing high/low, SL = sous/sur l'EMA50 (ou derrière la mèche si
     elle dépasse déjà l'EMA50 au moment du test)

STRATÉGIE 2 - Croisement EMA50/EMA200 + rejection :
  1. Un croisement EMA50/EMA200 doit s'être produit récemment
  2. Après le croisement, le prix revient tester la zone du croisement
  3. Confirmation : une bougie de rejection (mèche significative dans la zone,
     clôture qui ressort de l'autre côté)
  4. TP = prochain swing high/low, SL = derrière la mèche de rejection

Les deux stratégies sont indépendantes et évaluées en parallèle sur chaque actif.
Le TDI n'intervient PAS dans la stratégie 2 (confirmé explicitement par le
demandeur du projet).
"""

from dataclasses import dataclass
from typing import Optional
import pandas as pd

import config
import indicators
import risk_management


@dataclass
class SignalTrade:
    strategie: str  # "retest_ema50" ou "croisement_rejection" - jamais montré à l'utilisateur final
    direction: str
    niveaux: risk_management.NiveauxPosition


def _detecter_tendance(df_ind: pd.DataFrame) -> Optional[str]:
    """Tendance via écart EMA50/EMA200. None si l'écart est trop faible (marché plat)."""
    derniere = df_ind.iloc[-1]
    ema_fast, ema_slow = derniere["ema_fast"], derniere["ema_slow"]
    if pd.isna(ema_fast) or pd.isna(ema_slow):
        return None
    ecart_relatif = abs(ema_fast - ema_slow) / ema_slow
    if ecart_relatif < config.STRAT1_ECART_MIN_TENDANCE:
        return None
    return "ACHAT" if ema_fast > ema_slow else "VENTE"


def _prix_au_contact_ema50(df_ind: pd.DataFrame, index: int) -> bool:
    """Le prix (High/Low de la bougie) touche-t-il l'EMA50 à cet index ?"""
    row = df_ind.iloc[index]
    if pd.isna(row["ema_fast"]):
        return False
    ema50 = row["ema_fast"]
    # Contact = l'EMA50 se situe entre le Low et le High de la bougie (avec tolérance),
    # ou très proche du Close, pour couvrir les cas où le retest est net ou approximatif.
    dans_la_bougie = row["Low"] <= ema50 <= row["High"]
    proche_du_close = abs(row["Close"] - ema50) / ema50 < config.STRAT1_TOLERANCE_CONTACT_EMA50
    return dans_la_bougie or proche_du_close


def _rsi_rebondit_sur_50(df_ind: pd.DataFrame, index: int, direction: str) -> bool:
    """
    Le RSI rebondit-il sur sa ligne médiane (50) à cet index, dans le sens attendu ?

    Point de vigilance (leçon tirée d'un bug similaire sur un autre projet) : la
    condition est vérifiée AU MOMENT PRÉCIS du contact prix/EMA50 (paramètre `index`),
    pas sur une fenêtre glissante des dernières bougies dans l'absolu. Si on regardait
    uniquement "les 3 dernières bougies" sans ancrer au point de contact, un rebond
    rapide pourrait être raté parce que le RSI a déjà continué sa route au moment où
    le code regarde.
    """
    if index < 1:
        return False
    rsi_actuel = df_ind["tdi_rsi"].iloc[index]
    rsi_precedent = df_ind["tdi_rsi"].iloc[index - 1]
    if pd.isna(rsi_actuel) or pd.isna(rsi_precedent):
        return False

    zone_basse = 50 - config.STRAT1_ZONE_RSI_REBOND
    zone_haute = 50 + config.STRAT1_ZONE_RSI_REBOND
    dans_la_zone = zone_basse <= rsi_actuel <= zone_haute

    if not dans_la_zone:
        return False

    if direction == "ACHAT":
        return rsi_actuel >= rsi_precedent  # le RSI remonte au contact du 50
    else:  # VENTE
        return rsi_actuel <= rsi_precedent  # le RSI redescend au contact du 50


def _construire_sl_avec_meche(df_ind: pd.DataFrame, index: int, direction: str, niveau_reference: float) -> float:
    """
    Construit le SL en tenant compte d'une éventuelle mèche qui dépasse déjà le
    niveau de référence (EMA50 pour la stratégie 1, zone de croisement pour la 2).
    Si une mèche dépasse, le SL se place derrière elle avec une marge en ATR ;
    sinon, le SL se place juste derrière le niveau de référence lui-même.
    """
    row = df_ind.iloc[index]
    atr = row["atr"] if not pd.isna(row["atr"]) else 0
    marge = atr * config.MARGE_DERRIERE_MECHE_ATR

    if direction == "ACHAT":
        meche_depasse = row["Low"] < niveau_reference
        if meche_depasse:
            return row["Low"] - marge
        return niveau_reference - marge
    else:  # VENTE
        meche_depasse = row["High"] > niveau_reference
        if meche_depasse:
            return row["High"] + marge
        return niveau_reference + marge


def _evaluer_strategie1(symbol: str, asset_type: str, df_ind: pd.DataFrame) -> Optional[SignalTrade]:
    """Stratégie 1 : retest EMA50 + confirmation TDI. Vérifiée sur la dernière bougie close."""
    direction = _detecter_tendance(df_ind)
    if direction is None:
        return None

    index_actuel = len(df_ind) - 1

    if not _prix_au_contact_ema50(df_ind, index_actuel):
        return None
    if not _rsi_rebondit_sur_50(df_ind, index_actuel, direction):
        return None

    prix_entree = float(df_ind["Close"].iloc[index_actuel])
    ema50 = float(df_ind["ema_fast"].iloc[index_actuel])
    stop_loss = _construire_sl_avec_meche(df_ind, index_actuel, direction, ema50)

    if direction == "ACHAT":
        take_profit = risk_management.trouver_swing_high(df_ind, config.FENETRE_SWING_TP, exclure_derniere_n=1)
    else:
        take_profit = risk_management.trouver_swing_low(df_ind, config.FENETRE_SWING_TP, exclure_derniere_n=1)

    if take_profit is None:
        return None

    niveaux = risk_management.construire_niveaux(direction, prix_entree, stop_loss, take_profit, asset_type, symbol)
    if niveaux is None:
        return None

    return SignalTrade(strategie="retest_ema50", direction=direction, niveaux=niveaux)


def _trouver_croisement_recent(df_ind: pd.DataFrame, fenetre: int) -> Optional[tuple]:
    """
    Cherche un croisement EMA50/EMA200 dans les `fenetre` dernières bougies.
    Retourne (index_du_croisement, direction) ou None si aucun croisement trouvé.
    direction = "ACHAT" si EMA50 passe AU-DESSUS de EMA200 (croisement haussier),
                "VENTE" si EMA50 passe EN-DESSOUS de EMA200 (croisement baissier).
    """
    if len(df_ind) < fenetre + 1:
        return None

    zone = df_ind.iloc[-(fenetre + 1):]
    ema_fast = zone["ema_fast"]
    ema_slow = zone["ema_slow"]

    if ema_fast.isna().any() or ema_slow.isna().any():
        return None

    # On parcourt de la bougie la plus récente vers la plus ancienne pour trouver
    # le croisement le plus récent en premier.
    for i in range(len(zone) - 1, 0, -1):
        etait_en_dessous = ema_fast.iloc[i - 1] <= ema_slow.iloc[i - 1]
        est_au_dessus = ema_fast.iloc[i] > ema_slow.iloc[i]
        if etait_en_dessous and est_au_dessus:
            index_reel = len(df_ind) - (fenetre + 1) + i
            return (index_reel, "ACHAT")

        etait_au_dessus = ema_fast.iloc[i - 1] >= ema_slow.iloc[i - 1]
        est_en_dessous = ema_fast.iloc[i] < ema_slow.iloc[i]
        if etait_au_dessus and est_en_dessous:
            index_reel = len(df_ind) - (fenetre + 1) + i
            return (index_reel, "VENTE")

    return None


def _detecter_rejection(df_ind: pd.DataFrame, index: int, direction: str, niveau_zone: float) -> bool:
    """
    Une rejection = une bougie dont la mèche dépasse la zone testée, mais dont le
    corps (open/close) ne dépasse pas franchement de l'autre côté, avec une mèche
    jugée significative par rapport à la taille du corps (évite de valider sur une
    mèche insignifiante, du simple bruit de marché).
    """
    row = df_ind.iloc[index]
    corps = abs(row["Close"] - row["Open"])
    if corps == 0:
        corps = (row["High"] - row["Low"]) * 0.01  # évite une division par zéro sur un doji

    if direction == "VENTE":
        # Après un croisement baissier, on attend un retest par le haut avec rejection :
        # la mèche haute dépasse la zone, mais la clôture reste en dessous.
        meche_haute = row["High"] - max(row["Open"], row["Close"])
        touche_la_zone = row["High"] >= niveau_zone
        cloture_sous_la_zone = row["Close"] < niveau_zone
        meche_significative = meche_haute >= corps * config.STRAT2_RATIO_MECHE_MIN
        return touche_la_zone and cloture_sous_la_zone and meche_significative

    else:  # ACHAT
        meche_basse = min(row["Open"], row["Close"]) - row["Low"]
        touche_la_zone = row["Low"] <= niveau_zone
        cloture_au_dessus_de_la_zone = row["Close"] > niveau_zone
        meche_significative = meche_basse >= corps * config.STRAT2_RATIO_MECHE_MIN
        return touche_la_zone and cloture_au_dessus_de_la_zone and meche_significative


def _evaluer_strategie2(symbol: str, asset_type: str, df_ind: pd.DataFrame) -> Optional[SignalTrade]:
    """Stratégie 2 : croisement EMA50/EMA200 puis retest avec rejection."""
    croisement = _trouver_croisement_recent(df_ind, config.STRAT2_FENETRE_CROISEMENT)
    if croisement is None:
        return None

    index_croisement, direction_croisement = croisement
    index_actuel = len(df_ind) - 1

    # Le retest doit se produire dans une fenêtre raisonnable après le croisement,
    # ni immédiatement (pas encore de vrai retest) ni trop tard (le setup est expiré).
    bougies_depuis_croisement = index_actuel - index_croisement
    if bougies_depuis_croisement < 1 or bougies_depuis_croisement > config.STRAT2_FENETRE_RETEST:
        return None

    niveau_zone = float(df_ind["ema_fast"].iloc[index_actuel])  # la zone de croisement suit l'EMA50 actuelle

    if not _detecter_rejection(df_ind, index_actuel, direction_croisement, niveau_zone):
        return None

    prix_entree = float(df_ind["Close"].iloc[index_actuel])
    stop_loss = _construire_sl_avec_meche(df_ind, index_actuel, direction_croisement, niveau_zone)

    if direction_croisement == "ACHAT":
        take_profit = risk_management.trouver_swing_high(df_ind, config.FENETRE_SWING_TP, exclure_derniere_n=1)
    else:
        take_profit = risk_management.trouver_swing_low(df_ind, config.FENETRE_SWING_TP, exclure_derniere_n=1)

    if take_profit is None:
        return None

    niveaux = risk_management.construire_niveaux(direction_croisement, prix_entree, stop_loss, take_profit, asset_type, symbol)
    if niveaux is None:
        return None

    return SignalTrade(strategie="croisement_rejection", direction=direction_croisement, niveaux=niveaux)


def analyser_actif(symbol: str, asset_type: str, df: pd.DataFrame) -> Optional[SignalTrade]:
    """
    Point d'entrée principal : évalue les 2 stratégies sur un actif.
    Si les deux se valident au même cycle, la stratégie 1 (retest EMA50+TDI) est
    prioritaire, car elle a une confirmation multi-facteurs (prix + RSI) plus stricte
    que la stratégie 2 (mèche seule).
    """
    df_ind = indicators.calculer_tous_indicateurs(
        df, config.EMA_FAST, config.EMA_SLOW, config.ATR_PERIOD,
        config.TDI_RSI_PERIOD, config.TDI_RSI_PRICE_LINE, config.TDI_TRADE_SIGNAL_LINE, config.TDI_VOLATILITY_BAND,
    )

    signal1 = _evaluer_strategie1(symbol, asset_type, df_ind)
    if signal1 is not None:
        return signal1

    signal2 = _evaluer_strategie2(symbol, asset_type, df_ind)
    if signal2 is not None:
        return signal2

    return None
