"""
MAC Bot - Récupération des données de marché via Twelve Data

Transparence technique (à ne jamais retirer) :
Le plan gratuit Twelve Data a un délai documenté d'environ 1 à 15 minutes selon
l'actif - ce n'est pas du temps réel exact, même si généralement plus rapide que
Yahoo Finance. Ce module ne prétend jamais avoir une donnée plus fraîche que ce
que l'API renvoie réellement.

Rotation des clés : le code essaie la clé courante, et si Twelve Data répond avec
un code 429 (limite atteinte) ou 401/403 (clé invalide/épuisée), passe à la clé
suivante automatiquement. L'index de la clé "courante" est gardé en mémoire pour
toute la durée du processus (pas remis à zéro à chaque appel), afin de ne pas
retester inutilement des clés déjà identifiées comme épuisées dans le même cycle.
"""

import time
import logging
import requests
import pandas as pd

import config

logger = logging.getLogger("macbot.data_fetcher")


class DonneesInsuffisantesError(Exception):
    """Levée quand Twelve Data ne renvoie pas assez de bougies pour un calcul fiable."""
    pass


class ToutesLesClesEpuiseesError(Exception):
    """Levée quand les 4 clés API ont toutes atteint leur limite."""
    pass


class RotateurCles:
    """
    Garde en mémoire quelle clé API utiliser en priorité, sur la durée d'un
    processus. Ne réinitialise pas automatiquement - si une clé a été marquée
    épuisée, elle ne sera retentée qu'au prochain redémarrage du processus
    (ce qui, avec un cron toutes les 20 minutes, ne pose pas de souci pratique
    puisque le quota se régénère de toute façon avant le prochain cycle).
    """

    def __init__(self, cles: list):
        if not cles:
            raise ValueError("Aucune clé Twelve Data configurée")
        self.cles = cles
        self.index_courant = 0
        self.cles_epuisees = set()

    def cle_active(self) -> str:
        return self.cles[self.index_courant]

    def marquer_epuisee(self) -> bool:
        """
        Marque la clé courante comme épuisée et passe à la suivante.
        Retourne False si toutes les clés sont épuisées.
        """
        self.cles_epuisees.add(self.index_courant)
        for i in range(len(self.cles)):
            candidat = (self.index_courant + 1 + i) % len(self.cles)
            if candidat not in self.cles_epuisees:
                self.index_courant = candidat
                return True
        return False


_rotateur = RotateurCles(config.TWELVE_DATA_API_KEYS) if config.TWELVE_DATA_API_KEYS else None


def recuperer_bougies(symbol: str, interval: str, outputsize: int, min_candles: int,
                       max_retries_par_cle: int = 2) -> pd.DataFrame:
    """
    Récupère les bougies OHLCV pour un symbole donné, avec rotation automatique
    des clés API en cas de limite atteinte.

    Args:
        symbol: symbole Twelve Data (ex: "EUR/USD", "BTC/USD", "XAU/USD")
        interval: "15min", "1h", etc.
        outputsize: nombre de bougies demandées (max 5000 selon la doc Twelve Data)
        min_candles: nombre minimum de bougies exigé pour un calcul fiable
        max_retries_par_cle: tentatives avant de considérer une clé comme non-fonctionnelle

    Returns:
        DataFrame pandas avec colonnes Open/High/Low/Close, index = timestamps (ordre chronologique)

    Raises:
        DonneesInsuffisantesError: si les données renvoyées sont insuffisantes
        ToutesLesClesEpuiseesError: si les 4 clés ont toutes atteint leur limite
    """
    if _rotateur is None:
        raise ValueError("Aucune clé Twelve Data configurée dans les variables d'environnement")

    cles_essayees = 0

    while cles_essayees < len(_rotateur.cles):
        cle = _rotateur.cle_active()

        for tentative in range(1, max_retries_par_cle + 1):
            try:
                params = {
                    "symbol": symbol,
                    "interval": interval,
                    "outputsize": outputsize,
                    "apikey": cle,
                    "order": "ASC",  # chronologique, plus ancien en premier
                }
                response = requests.get(config.TWELVE_DATA_BASE_URL, params=params, timeout=20)
                data = response.json()

                # Twelve Data renvoie un code d'erreur dans le corps JSON, pas toujours
                # via le status code HTTP - il faut vérifier les deux.
                if isinstance(data, dict) and data.get("status") == "error":
                    code = data.get("code")
                    message = data.get("message", "")

                    if code in (429, 401, 403) or "limit" in message.lower() or "credit" in message.lower():
                        logger.warning(f"Clé API épuisée/invalide ({code}: {message}) - rotation")
                        if not _rotateur.marquer_epuisee():
                            raise ToutesLesClesEpuiseesError(
                                "Les 4 clés Twelve Data ont toutes atteint leur limite ce cycle"
                            )
                        cles_essayees += 1
                        break  # sort de la boucle de retry, passe à la clé suivante

                    # Autre type d'erreur (symbole invalide, etc.) - pas la peine de réessayer
                    raise DonneesInsuffisantesError(f"{symbol}: erreur Twelve Data ({code}: {message})")

                if "values" not in data or not data["values"]:
                    raise DonneesInsuffisantesError(f"{symbol}: aucune donnée renvoyée par Twelve Data")

                df = pd.DataFrame(data["values"])
                df["datetime"] = pd.to_datetime(df["datetime"])
                df = df.set_index("datetime")
                for col in ["open", "high", "low", "close"]:
                    df[col] = df[col].astype(float)
                df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"})
                df = df[["Open", "High", "Low", "Close"]]

                if len(df) < min_candles:
                    raise DonneesInsuffisantesError(
                        f"{symbol}: seulement {len(df)} bougies disponibles (minimum requis: {min_candles})"
                    )

                logger.info(f"{symbol} [{interval}]: {len(df)} bougies récupérées (clé index {_rotateur.index_courant})")
                return df

            except (DonneesInsuffisantesError, ToutesLesClesEpuiseesError):
                raise

            except requests.exceptions.RequestException as e:
                logger.warning(f"{symbol}: tentative {tentative}/{max_retries_par_cle} échouée ({e})")
                if tentative < max_retries_par_cle:
                    time.sleep(2 * tentative)

        else:
            # La boucle for s'est terminée sans break ni return -> échecs réseau répétés sur cette clé
            cles_essayees += 1
            if not _rotateur.marquer_epuisee():
                raise ToutesLesClesEpuiseesError(f"{symbol}: échec sur toutes les clés après erreurs réseau répétées")

    raise ToutesLesClesEpuiseesError(f"{symbol}: impossible de récupérer les données (toutes clés épuisées)")


def prix_actuel(symbol: str) -> float:
    """
    Récupère le dernier prix de clôture connu, pour vérifier si un TP/SL est touché.
    Réutilise recuperer_bougies avec une petite fenêtre pour limiter la consommation de quota.
    """
    df = recuperer_bougies(symbol, interval=config.TIMEFRAME, outputsize=2, min_candles=1)
    return float(df["Close"].iloc[-1])
