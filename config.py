"""
MAC Bot - Configuration centrale

Toutes les valeurs modifiables sont ici. Rien n'est en dur ailleurs dans le code.
"""

import os

# ============================================================
# TELEGRAM
# ============================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")  # canal des signaux

# ============================================================
# TWELVE DATA - rotation de 4 clés API
# ============================================================
# Chaque clé gratuite : 8 appels/minute, 800 appels/jour.
# Avec rotation sur 4 clés : jusqu'à 3200 appels/jour cumulés.
# Le code passe à la clé suivante dès qu'une limite est atteinte (code 429),
# jamais en fonction d'un simple compteur local, pour rester robuste même si
# une clé a déjà été partiellement utilisée par un autre processus.
TWELVE_DATA_API_KEYS = [
    os.environ.get("TWELVE_DATA_KEY_1", ""),
    os.environ.get("TWELVE_DATA_KEY_2", ""),
    os.environ.get("TWELVE_DATA_KEY_3", ""),
    os.environ.get("TWELVE_DATA_KEY_4", ""),
]
TWELVE_DATA_API_KEYS = [k for k in TWELVE_DATA_API_KEYS if k]  # retire les clés vides

TWELVE_DATA_BASE_URL = "https://api.twelvedata.com/time_series"

# Limite technique du plan gratuit Twelve Data (documentée : 8 req/min, 800 req/jour par clé).
# Utilisé pour espacer les appels et éviter de déclencher des 429 évitables.
TWELVE_DATA_MAX_CALLS_PER_MINUTE_PER_KEY = 8
TWELVE_DATA_MIN_DELAY_BETWEEN_CALLS_SECONDS = 8  # marge de sécurité (60s / 8 ≈ 7.5s, arrondi à 8s)

# ============================================================
# ACTIFS SUIVIS (mêmes 24 que MR EMA, cohérence entre les deux projets)
# ============================================================
# Format Twelve Data : "EUR/USD", "XAU/USD", "BTC/USD" (avec slash, contrairement à yfinance)
ASSETS = {
    "XAUUSD": {"symbol": "XAU/USD", "type": "metal", "display": "XAU/USD (Or)"},
    "XAGUSD": {"symbol": "XAG/USD", "type": "metal", "display": "XAG/USD (Argent)"},
    "BTCUSD": {"symbol": "BTC/USD", "type": "crypto", "display": "BTC/USD"},
    "GBPUSD": {"symbol": "GBP/USD", "type": "forex", "display": "GBP/USD"},
    "EURUSD": {"symbol": "EUR/USD", "type": "forex", "display": "EUR/USD"},
    "USDJPY": {"symbol": "USD/JPY", "type": "forex", "display": "USD/JPY"},
    "USDCHF": {"symbol": "USD/CHF", "type": "forex", "display": "USD/CHF"},
    "AUDUSD": {"symbol": "AUD/USD", "type": "forex", "display": "AUD/USD"},
    "USDCAD": {"symbol": "USD/CAD", "type": "forex", "display": "USD/CAD"},
    "NZDUSD": {"symbol": "NZD/USD", "type": "forex", "display": "NZD/USD"},
    "EURJPY": {"symbol": "EUR/JPY", "type": "forex", "display": "EUR/JPY"},
    "GBPJPY": {"symbol": "GBP/JPY", "type": "forex", "display": "GBP/JPY"},
    "EURGBP": {"symbol": "EUR/GBP", "type": "forex", "display": "EUR/GBP"},
    "AUDJPY": {"symbol": "AUD/JPY", "type": "forex", "display": "AUD/JPY"},
    "EURAUD": {"symbol": "EUR/AUD", "type": "forex", "display": "EUR/AUD"},
    "GBPAUD": {"symbol": "GBP/AUD", "type": "forex", "display": "GBP/AUD"},
    "GBPCAD": {"symbol": "GBP/CAD", "type": "forex", "display": "GBP/CAD"},
    "EURCAD": {"symbol": "EUR/CAD", "type": "forex", "display": "EUR/CAD"},
    "AUDCAD": {"symbol": "AUD/CAD", "type": "forex", "display": "AUD/CAD"},
    "AUDNZD": {"symbol": "AUD/NZD", "type": "forex", "display": "AUD/NZD"},
    "CADJPY": {"symbol": "CAD/JPY", "type": "forex", "display": "CAD/JPY"},
    "CHFJPY": {"symbol": "CHF/JPY", "type": "forex", "display": "CHF/JPY"},
    "NZDJPY": {"symbol": "NZD/JPY", "type": "forex", "display": "NZD/JPY"},
    "EURCHF": {"symbol": "EUR/CHF", "type": "forex", "display": "EUR/CHF"},
}

# ============================================================
# TIMEFRAME - un seul, contrainte du plan gratuit Twelve Data
# ============================================================
TIMEFRAME = "15min"
CANDLES_REQUESTED = 1000
MIN_CANDLES_REQUIRED = 210  # marge au-dessus de EMA200 pour un calcul fiable

# ============================================================
# INDICATEURS
# ============================================================
EMA_FAST = 50
EMA_SLOW = 200

TDI_RSI_PERIOD = 13
TDI_RSI_PRICE_LINE = 2
TDI_TRADE_SIGNAL_LINE = 7
TDI_VOLATILITY_BAND = 34

ATR_PERIOD = 14  # utilisé uniquement pour la marge derrière une mèche de rejection

# ============================================================
# STRATÉGIE 1 - Retest EMA50 + confirmation TDI
# ============================================================
# Écart minimum entre EMA50 et EMA200 pour juger la tendance "assez nette" (évite de trader
# un marché plat où les deux EMA sont collées, source de faux signaux).
STRAT1_ECART_MIN_TENDANCE = 0.0006  # 0.06%, un peu plus large qu'en H1 vu qu'on est en M15

# Le prix est considéré "au contact" de l'EMA50 si l'écart est inférieur à ce pourcentage
STRAT1_TOLERANCE_CONTACT_EMA50 = 0.0012  # 0.12%

# Le RSI est considéré "proche de 50" (pour le rebond) dans cette bande
STRAT1_ZONE_RSI_REBOND = 6  # RSI entre 44 et 56 = zone de rebond valide sur la ligne 50

# ============================================================
# STRATÉGIE 2 - Croisement EMA50/EMA200 + rejection
# ============================================================
# Nombre de bougies en arrière dans lesquelles on cherche un croisement récent
STRAT2_FENETRE_CROISEMENT = 30

# Après le croisement, nombre de bougies pendant lesquelles on autorise un retest+rejection
STRAT2_FENETRE_RETEST = 15

# Une mèche est jugée significative (donc "rejection") si elle représente au moins ce
# pourcentage du corps de la bougie - évite de valider un signal sur une mèche minuscule
STRAT2_RATIO_MECHE_MIN = 0.5

# ============================================================
# RISK MANAGEMENT (règle non-négociable, commune aux deux stratégies)
# ============================================================
MIN_RISK_REWARD = 1.50
MAX_RISK_REWARD = 3.50

# Marge ajoutée derrière une mèche pour le SL (en multiple d'ATR, pour que la marge
# s'adapte à la volatilité de l'actif plutôt que d'être une valeur fixe en pips)
MARGE_DERRIERE_MECHE_ATR = 0.15

# Fenêtre de recherche du swing high/low le plus récent pour le TP
FENETRE_SWING_TP = 40

# ============================================================
# HORAIRES (Burkina Faso = UTC+0 toute l'année)
# ============================================================
TIMEZONE_BF = "Africa/Ouagadougou"
MORNING_HOUR_BF = 7
EVENING_HOUR_BF = 20

# ============================================================
# CRON EXTERNE (cron-job.org appelle cet endpoint toutes les 20 min)
# ============================================================
CRON_SECRET = os.environ.get("CRON_SECRET", "")  # protège l'endpoint contre des appels non désirés

# ============================================================
# BASE DE DONNÉES
# ============================================================
DATABASE_PATH = os.environ.get("DATABASE_PATH", "data/macbot.db")

# ============================================================
# ACCÈS "CANAUX TELEGRAM" (fonctionnalité protégée par mot de passe)
# ============================================================
PASSWORD_CANAUX_TELEGRAM = os.environ.get("PASSWORD_CANAUX_TELEGRAM", "")

# ============================================================
# SUPPORT
# ============================================================
SUPPORT_TELEGRAM_URL = "https://t.me/Sienouobedalai226"

# ============================================================
# CANAL OFFICIEL DES SIGNAUX (affiché dans la commande /canaux)
# À renseigner : lien public du canal où le chat_id -1004475850376 pointe.
# ============================================================
CANAL_SIGNAUX_URL = os.environ.get("CANAL_SIGNAUX_URL", "")

# ============================================================
# DAY TRADING - durée de vie max d'une position (cohérence avec MR EMA)
# ============================================================
MAX_POSITION_HOURS = 18
