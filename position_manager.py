"""
MAC Bot - Gestion des positions ouvertes

Contrairement à MR EMA (fichiers JSON versionnés dans Git), MAC Bot utilise SQLite
via database.py pour stocker l'état - plus adapté à un web service Render qui tourne
en continu plutôt qu'à des runs cron isolés GitHub Actions.
"""

import logging
from datetime import datetime, timezone

import config
import database
import risk_management

logger = logging.getLogger("macbot.position_manager")


def ouvrir_position(symbol: str, display: str, asset_type: str, signal) -> database.PositionDB:
    maintenant = datetime.now(timezone.utc).isoformat()
    position_id = f"{symbol.replace('/', '')}_{maintenant}"

    position = database.PositionDB(
        id=position_id,
        symbol=symbol,
        display=display,
        asset_type=asset_type,
        strategie=signal.strategie,  # stocké en base pour analyse interne, jamais montré à l'utilisateur
        direction=signal.direction,
        prix_entree=signal.niveaux.prix_entree,
        stop_loss=signal.niveaux.stop_loss,
        take_profit=signal.niveaux.take_profit,
        ratio_rr=signal.niveaux.ratio_rr,
        pips_risque=signal.niveaux.pips_risque,
        ouverte_le=maintenant,
    )
    database.ajouter_position(position)
    return position


def _niveau_touche(direction: str, prix_actuel: float, niveau: float, est_tp: bool) -> bool:
    if direction == "ACHAT":
        return prix_actuel >= niveau if est_tp else prix_actuel <= niveau
    else:
        return prix_actuel <= niveau if est_tp else prix_actuel >= niveau


def verifier_position(position: dict, prix_actuel: float) -> tuple:
    """
    Vérifie si le TP ou le SL d'une position est touché.
    Retourne (evenement, resultat_pips) où evenement est "TP_TOUCHE", "SL_TOUCHE", ou None.
    """
    if _niveau_touche(position["direction"], prix_actuel, position["stop_loss"], est_tp=False):
        resultat = -position["pips_risque"]
        return ("SL_TOUCHE", resultat)

    if _niveau_touche(position["direction"], prix_actuel, position["take_profit"], est_tp=True):
        resultat = position["ratio_rr"] * position["pips_risque"]
        return ("TP_TOUCHE", resultat)

    return (None, None)


def verifier_expiration_day_trading(position: dict) -> bool:
    ouverte = datetime.fromisoformat(position["ouverte_le"])
    maintenant = datetime.now(timezone.utc)
    duree_heures = (maintenant - ouverte).total_seconds() / 3600
    return duree_heures >= config.MAX_POSITION_HOURS


def cloturer_position(position: dict, resultat_pips: float, statut_final: str) -> None:
    fermee_le = datetime.now(timezone.utc).isoformat()
    database.ajouter_a_historique(position, resultat_pips, statut_final, fermee_le)
    database.supprimer_position_ouverte(position["id"])
