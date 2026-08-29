"""
MAC Bot - Indicateurs techniques

EMA et ATR utilisent des formules standards. Le TDI est recalculé à partir de sa
définition originale (RSI lissé + bandes de Bollinger sur ce RSI), comme dans MR EMA -
il n'existe pas nativement dans les librairies Python courantes.

Contrairement à MR EMA, pas de MACD ici : les 2 stratégies BTMM de ce projet
n'en ont pas besoin (retest EMA50+TDI, et croisement EMA50/200+rejection).
"""

import pandas as pd
import numpy as np


def calculer_ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def calculer_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    close_prec = close.shift(1)
    tr1 = high - low
    tr2 = (high - close_prec).abs()
    tr3 = (low - close_prec).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return atr


def calculer_rsi(close: pd.Series, period: int = 13) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.fillna(50)
    return rsi


def calculer_tdi(close: pd.Series, rsi_period: int = 13, price_line_period: int = 2,
                  signal_period: int = 7, volatility_band_period: int = 34) -> pd.DataFrame:
    """
    Retourne un DataFrame avec: rsi, price_line, signal_line, bb_upper, bb_lower, bb_mid
    """
    rsi = calculer_rsi(close, rsi_period)
    price_line = rsi.rolling(window=price_line_period).mean()
    signal_line = rsi.rolling(window=signal_period).mean()
    bb_mid = rsi.rolling(window=volatility_band_period).mean()
    bb_std = rsi.rolling(window=volatility_band_period).std()
    bb_upper = bb_mid + (bb_std * 1.6185)
    bb_lower = bb_mid - (bb_std * 1.6185)

    return pd.DataFrame({
        "rsi": rsi,
        "price_line": price_line,
        "signal_line": signal_line,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "bb_mid": bb_mid,
    })


def calculer_tous_indicateurs(df: pd.DataFrame, ema_fast: int, ema_slow: int, atr_period: int,
                                tdi_rsi_period: int, tdi_price_line: int, tdi_signal_line: int,
                                tdi_bb_period: int) -> pd.DataFrame:
    """Ajoute toutes les colonnes d'indicateurs à un DataFrame OHLC. Retourne une copie."""
    result = df.copy()

    result["ema_fast"] = calculer_ema(df["Close"], ema_fast)
    result["ema_slow"] = calculer_ema(df["Close"], ema_slow)
    result["atr"] = calculer_atr(df["High"], df["Low"], df["Close"], atr_period)

    tdi_df = calculer_tdi(df["Close"], tdi_rsi_period, tdi_price_line, tdi_signal_line, tdi_bb_period)
    result["tdi_rsi"] = tdi_df["rsi"]
    result["tdi_price_line"] = tdi_df["price_line"]
    result["tdi_signal_line"] = tdi_df["signal_line"]

    return result
