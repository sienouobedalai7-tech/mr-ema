"""
MAC Bot - Base de données SQLite

Stocke : les utilisateurs inscrits (identifiés par leur user_id Telegram, pas de
mot de passe), les positions ouvertes, et l'historique des positions clôturées.

Note sur la persistance (Render gratuit) : le disque survit tant que le service
ne redéploie pas. Un redéploiement (nouveau push de code) réinitialise le disque,
donc la base est perdue à ce moment précis. C'est une limite du plan gratuit
Render à connaître, pas un bug de ce module - voir le README pour les détails.
"""

import sqlite3
import os
import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional
from contextlib import contextmanager

import config

logger = logging.getLogger("macbot.database")


def initialiser_base():
    """Crée les tables si elles n'existent pas déjà. Appelé au démarrage du serveur."""
    os.makedirs(os.path.dirname(config.DATABASE_PATH), exist_ok=True)
    with _connexion() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS utilisateurs (
                user_id INTEGER PRIMARY KEY,
                nom TEXT NOT NULL,
                nom_profil_telegram TEXT,
                inscrit_le TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS positions_ouvertes (
                id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                display TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                strategie TEXT NOT NULL,
                direction TEXT NOT NULL,
                prix_entree REAL NOT NULL,
                stop_loss REAL NOT NULL,
                take_profit REAL NOT NULL,
                ratio_rr REAL NOT NULL,
                pips_risque REAL NOT NULL,
                ouverte_le TEXT NOT NULL,
                statut TEXT NOT NULL DEFAULT 'OUVERTE'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS historique (
                id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                display TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                direction TEXT NOT NULL,
                prix_entree REAL NOT NULL,
                stop_loss REAL NOT NULL,
                take_profit REAL NOT NULL,
                ratio_rr REAL NOT NULL,
                resultat_pips REAL,
                statut_final TEXT NOT NULL,
                ouverte_le TEXT NOT NULL,
                fermee_le TEXT NOT NULL
            )
        """)
        conn.commit()
    logger.info("Base de données initialisée")


@contextmanager
def _connexion():
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# ============================================================
# UTILISATEURS
# ============================================================

def utilisateur_existe(user_id: int) -> bool:
    with _connexion() as conn:
        row = conn.execute("SELECT 1 FROM utilisateurs WHERE user_id = ?", (user_id,)).fetchone()
        return row is not None


def inscrire_utilisateur(user_id: int, nom: str, nom_profil_telegram: Optional[str] = None) -> None:
    with _connexion() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO utilisateurs (user_id, nom, nom_profil_telegram, inscrit_le) VALUES (?, ?, ?, ?)",
            (user_id, nom, nom_profil_telegram, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def obtenir_utilisateur(user_id: int) -> Optional[dict]:
    with _connexion() as conn:
        row = conn.execute("SELECT * FROM utilisateurs WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


# ============================================================
# POSITIONS OUVERTES
# ============================================================

@dataclass
class PositionDB:
    id: str
    symbol: str
    display: str
    asset_type: str
    strategie: str
    direction: str
    prix_entree: float
    stop_loss: float
    take_profit: float
    ratio_rr: float
    pips_risque: float
    ouverte_le: str
    statut: str = "OUVERTE"


def ajouter_position(position: PositionDB) -> None:
    with _connexion() as conn:
        conn.execute("""
            INSERT INTO positions_ouvertes
            (id, symbol, display, asset_type, strategie, direction, prix_entree, stop_loss,
             take_profit, ratio_rr, pips_risque, ouverte_le, statut)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (position.id, position.symbol, position.display, position.asset_type, position.strategie,
              position.direction, position.prix_entree, position.stop_loss, position.take_profit,
              position.ratio_rr, position.pips_risque, position.ouverte_le, position.statut))
        conn.commit()


def lister_positions_ouvertes() -> list:
    with _connexion() as conn:
        rows = conn.execute("SELECT * FROM positions_ouvertes").fetchall()
        return [dict(row) for row in rows]


def symbole_a_deja_une_position_ouverte(symbol: str) -> bool:
    with _connexion() as conn:
        row = conn.execute("SELECT 1 FROM positions_ouvertes WHERE symbol = ?", (symbol,)).fetchone()
        return row is not None


def supprimer_position_ouverte(position_id: str) -> None:
    with _connexion() as conn:
        conn.execute("DELETE FROM positions_ouvertes WHERE id = ?", (position_id,))
        conn.commit()


def mettre_a_jour_statut_position(position_id: str, nouveau_statut: str) -> None:
    with _connexion() as conn:
        conn.execute("UPDATE positions_ouvertes SET statut = ? WHERE id = ?", (nouveau_statut, position_id))
        conn.commit()


# ============================================================
# HISTORIQUE
# ============================================================

def ajouter_a_historique(position: dict, resultat_pips: Optional[float], statut_final: str, fermee_le: str) -> None:
    with _connexion() as conn:
        conn.execute("""
            INSERT INTO historique
            (id, symbol, display, asset_type, direction, prix_entree, stop_loss, take_profit,
             ratio_rr, resultat_pips, statut_final, ouverte_le, fermee_le)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (position["id"], position["symbol"], position["display"], position["asset_type"],
              position["direction"], position["prix_entree"], position["stop_loss"], position["take_profit"],
              position["ratio_rr"], resultat_pips, statut_final, position["ouverte_le"], fermee_le))
        conn.commit()


def positions_fermees_aujourdhui() -> list:
    """Retourne les positions de l'historique fermées à la date du jour (UTC)."""
    aujourdhui = datetime.now(timezone.utc).date().isoformat()
    with _connexion() as conn:
        rows = conn.execute(
            "SELECT * FROM historique WHERE fermee_le LIKE ? ORDER BY fermee_le", (f"{aujourdhui}%",)
        ).fetchall()
        return [dict(row) for row in rows]


def positions_ouvertes_ou_fermees_aujourdhui_pour_signaux() -> list:
    """
    Utilisé par la commande /signaux : toutes les positions du jour, ouvertes ou fermées,
    triées par heure d'ouverture. Combine positions_ouvertes (encore actives) et
    l'historique du jour (déjà fermées).
    """
    aujourdhui = datetime.now(timezone.utc).date().isoformat()
    resultats = []

    with _connexion() as conn:
        rows_ouvertes = conn.execute(
            "SELECT * FROM positions_ouvertes WHERE ouverte_le LIKE ? ORDER BY ouverte_le", (f"{aujourdhui}%",)
        ).fetchall()
        resultats.extend([dict(row) for row in rows_ouvertes])

        rows_historique = conn.execute(
            "SELECT * FROM historique WHERE ouverte_le LIKE ? ORDER BY ouverte_le", (f"{aujourdhui}%",)
        ).fetchall()
        resultats.extend([dict(row) for row in rows_historique])

    resultats.sort(key=lambda p: p["ouverte_le"])
    return resultats
