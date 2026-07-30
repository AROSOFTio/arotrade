from __future__ import annotations

from app.services.scanner import indicators


def _series(candles: list[dict], key: str) -> list[float]:
    return [float(c[key]) for c in candles if c.get(key) is not None]


def vwap(candles: list[dict]) -> float | None:
    total_pv = 0.0
    total_volume = 0.0
    for candle in candles:
        volume = float(candle.get("volume") or candle.get("tickVolume") or 0)
        if volume <= 0:
            continue
        typical = (float(candle["high"]) + float(candle["low"]) + float(candle["close"])) / 3
        total_pv += typical * volume
        total_volume += volume
    return total_pv / total_volume if total_volume else None


def bollinger_bands(closes: list[float], period: int = 20, deviations: float = 2.0) -> dict | None:
    if len(closes) < period:
        return None
    window = closes[-period:]
    mid = sum(window) / period
    variance = sum((price - mid) ** 2 for price in window) / period
    width = variance ** 0.5
    return {"lower": mid - deviations * width, "middle": mid, "upper": mid + deviations * width}


def market_snapshot(symbol: str, timeframe: str, candles: list[dict]) -> dict:
    closes = _series(candles, "close")
    latest = candles[-1] if candles else None
    levels = indicators.support_resistance_levels(candles, lookback=5) if len(candles) >= 15 else {"support": [], "resistance": []}
    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "latest_candle": latest,
        "trend": indicators.trend_structure(closes),
        "moving_averages": {
            "ema20": indicators.ema(closes, 20),
            "ema50": indicators.ema(closes, 50),
            "ema200": indicators.ema(closes, 200),
            "sma20": indicators.sma(closes, 20),
            "sma50": indicators.sma(closes, 50),
        },
        "momentum": {
            "rsi14": indicators.rsi(closes, 14),
            "macd": indicators.macd(closes),
        },
        "volatility": {
            "atr14": indicators.atr(candles, 14),
            "normalised_atr14": indicators.normalised_atr(candles, 14),
            "bollinger20": bollinger_bands(closes, 20),
        },
        "volume": {"vwap": vwap(candles)},
        "structure": {
            "support": levels["support"][:5],
            "resistance": levels["resistance"][:5],
            "swing_highs": indicators.swing_highs(candles, 5)[-5:],
            "swing_lows": indicators.swing_lows(candles, 5)[-5:],
        },
    }

