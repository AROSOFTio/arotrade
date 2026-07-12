"""Pure technical-analysis indicator calculations.

All functions are stateless and work on plain lists/dicts of OHLCV candles.
No database access, no HTTP calls — purely deterministic math.

Candle format expected:
  {"time": ..., "open": float, "high": float, "low": float, "close": float}

All functions return None when insufficient data is available rather than
crashing or returning misleading values.
"""

from __future__ import annotations

import math
from typing import Optional


# ---------------------------------------------------------------------------
# Moving Averages
# ---------------------------------------------------------------------------

def ema(closes: list[float], period: int) -> Optional[float]:
    """Exponential Moving Average of the last `period` closes."""
    if len(closes) < period:
        return None
    k = 2.0 / (period + 1)
    ema_val = sum(closes[:period]) / period
    for price in closes[period:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val


def ema_series(closes: list[float], period: int) -> list[float]:
    """Full EMA series (same length as closes, NaN-filled for initial values)."""
    if len(closes) < period:
        return [float("nan")] * len(closes)
    k = 2.0 / (period + 1)
    result = [float("nan")] * (period - 1)
    current = sum(closes[:period]) / period
    result.append(current)
    for price in closes[period:]:
        current = price * k + current * (1 - k)
        result.append(current)
    return result


def sma(closes: list[float], period: int) -> Optional[float]:
    """Simple Moving Average."""
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------

def rsi(closes: list[float], period: int = 14) -> Optional[float]:
    """
    RSI (Wilder's smoothing).
    Returns a value in [0, 100] or None if insufficient data.
    """
    if len(closes) < period + 1:
        return None

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

def macd(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> Optional[dict]:
    """
    MACD line, signal line, and histogram.
    Returns None if insufficient data.
    Returns: {"macd": float, "signal": float, "histogram": float}
    """
    min_len = slow + signal_period - 1
    if len(closes) < min_len:
        return None

    fast_series = ema_series(closes, fast)
    slow_series = ema_series(closes, slow)
    macd_line = [
        f - s
        for f, s in zip(fast_series, slow_series)
        if not (math.isnan(f) or math.isnan(s))
    ]
    if len(macd_line) < signal_period:
        return None

    signal_series = ema_series(macd_line, signal_period)
    last_macd = macd_line[-1]
    last_signal = signal_series[-1]
    if math.isnan(last_signal):
        return None

    return {
        "macd": last_macd,
        "signal": last_signal,
        "histogram": last_macd - last_signal,
    }


# ---------------------------------------------------------------------------
# ATR
# ---------------------------------------------------------------------------

def atr(candles: list[dict], period: int = 14) -> Optional[float]:
    """
    Average True Range.
    Returns None if insufficient data.
    """
    if len(candles) < period + 1:
        return None

    trs = []
    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_close = candles[i - 1]["close"]
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )
        trs.append(tr)

    # Wilder's smoothing
    atr_val = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr_val = (atr_val * (period - 1) + tr) / period
    return atr_val


# ---------------------------------------------------------------------------
# Swing highs / lows
# ---------------------------------------------------------------------------

def swing_highs(candles: list[dict], lookback: int = 5) -> list[dict]:
    """
    Identify swing highs: a candle whose high is higher than `lookback`
    candles on each side.
    Returns a list of {"index": int, "price": float, "time": ...}.
    """
    result = []
    for i in range(lookback, len(candles) - lookback):
        if all(candles[i]["high"] >= candles[j]["high"] for j in range(i - lookback, i + lookback + 1) if j != i):
            result.append({"index": i, "price": candles[i]["high"], "time": candles[i].get("time")})
    return result


def swing_lows(candles: list[dict], lookback: int = 5) -> list[dict]:
    """
    Identify swing lows: a candle whose low is lower than `lookback`
    candles on each side.
    """
    result = []
    for i in range(lookback, len(candles) - lookback):
        if all(candles[i]["low"] <= candles[j]["low"] for j in range(i - lookback, i + lookback + 1) if j != i):
            result.append({"index": i, "price": candles[i]["low"], "time": candles[i].get("time")})
    return result


# ---------------------------------------------------------------------------
# Support / Resistance
# ---------------------------------------------------------------------------

def support_resistance_levels(
    candles: list[dict],
    lookback: int = 5,
    tolerance_pct: float = 0.002,
) -> dict:
    """
    Cluster swing highs and lows into support and resistance zones.

    Returns:
      {
        "resistance": list[float],   # Ordered low → high
        "support": list[float],      # Ordered high → low
      }
    """
    highs = [s["price"] for s in swing_highs(candles, lookback)]
    lows = [s["price"] for s in swing_lows(candles, lookback)]

    def cluster(prices: list[float]) -> list[float]:
        if not prices:
            return []
        sorted_prices = sorted(prices)
        clusters = [[sorted_prices[0]]]
        for p in sorted_prices[1:]:
            mid = sum(clusters[-1]) / len(clusters[-1])
            if abs(p - mid) / mid <= tolerance_pct:
                clusters[-1].append(p)
            else:
                clusters.append([p])
        return [sum(c) / len(c) for c in clusters]

    return {
        "resistance": sorted(cluster(highs)),
        "support": sorted(cluster(lows), reverse=True),
    }


# ---------------------------------------------------------------------------
# Trend structure
# ---------------------------------------------------------------------------

def trend_structure(closes: list[float]) -> str:
    """
    Basic trend classification based on EMA alignment.
    Returns "bullish", "bearish", or "sideways".
    """
    e20 = ema(closes, 20)
    e50 = ema(closes, 50)
    e200 = ema(closes, 200)

    if e20 is None or e50 is None:
        return "sideways"

    if e200 is not None:
        if e20 > e50 > e200:
            return "bullish"
        if e20 < e50 < e200:
            return "bearish"
        return "sideways"

    if e20 > e50:
        return "bullish"
    if e20 < e50:
        return "bearish"
    return "sideways"


# ---------------------------------------------------------------------------
# Volatility
# ---------------------------------------------------------------------------

def normalised_atr(candles: list[dict], period: int = 14) -> Optional[float]:
    """ATR as a fraction of current price (dimensionless)."""
    if not candles:
        return None
    atr_val = atr(candles, period)
    if atr_val is None:
        return None
    price = candles[-1]["close"]
    if price <= 0:
        return None
    return atr_val / price


# ---------------------------------------------------------------------------
# Spread helpers (broker-specific)
# ---------------------------------------------------------------------------

def spread_in_points(bid: float, ask: float, point: float) -> Optional[float]:
    """Convert spread from price to points."""
    if point <= 0:
        return None
    return round((ask - bid) / point, 1)
