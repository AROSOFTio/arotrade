"""Free live market data via Deriv's public WebSocket API.

No API key required for market data; DERIV_APP_ID (or the public 1089 test id)
identifies the app. Provides candles and latest prices for forex majors and
crosses, metals, stock indices, crypto and Deriv synthetic indices — used by
the in-app charts, the AI analysis price context, and the backtesting engine.
"""

import json
import threading
import time
from typing import Optional

import websocket

from app.config import settings

# Platform symbol -> Deriv symbol
SYMBOL_MAP: dict[str, str] = {
    # Forex majors
    "EURUSD": "frxEURUSD", "GBPUSD": "frxGBPUSD", "USDJPY": "frxUSDJPY",
    "USDCHF": "frxUSDCHF", "AUDUSD": "frxAUDUSD", "NZDUSD": "frxNZDUSD", "USDCAD": "frxUSDCAD",
    # Crosses
    "EURGBP": "frxEURGBP", "EURJPY": "frxEURJPY", "GBPJPY": "frxGBPJPY",
    "AUDJPY": "frxAUDJPY", "CADJPY": "frxCADJPY", "CHFJPY": "frxCHFJPY",
    "EURAUD": "frxEURAUD", "EURCHF": "frxEURCHF", "GBPAUD": "frxGBPAUD",
    "GBPCAD": "frxGBPCAD", "AUDNZD": "frxAUDNZD", "NZDJPY": "frxNZDJPY",
    # Metals
    "XAUUSD": "frxXAUUSD", "XAGUSD": "frxXAGUSD", "XPTUSD": "frxXPTUSD",
    # Indices (OTC)
    "US30": "OTC_DJI", "US100": "OTC_NDX", "US500": "OTC_SPC",
    "GER40": "OTC_GDAXI", "UK100": "OTC_FTSE", "FRA40": "OTC_FCHI",
    "JPN225": "OTC_N225", "AUS200": "OTC_AS51", "HK50": "OTC_HSI",
    # Crypto
    "BTCUSD": "cryBTCUSD", "ETHUSD": "cryETHUSD",
    # Deriv synthetics
    "V10": "R_10", "V25": "R_25", "V50": "R_50", "V75": "R_75", "V100": "R_100",
    "BOOM1000": "BOOM1000", "CRASH1000": "CRASH1000", "STEP": "stpRNG",
}

GRANULARITY: dict[str, int] = {
    "M1": 60, "M5": 300, "M15": 900, "M30": 1800,
    "H1": 3600, "H4": 14400, "D1": 86400,
}

_WS_URL = "wss://ws.derivws.com/websockets/v3?app_id={app_id}"

# Tiny in-process cache: (symbol, timeframe, count) -> (expires_at, candles)
_cache: dict[tuple, tuple[float, list]] = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 20.0


class MarketDataError(Exception):
    pass


def supported_symbols() -> list[str]:
    return sorted(SYMBOL_MAP.keys())


def _app_id() -> str:
    return settings.DERIV_APP_ID or "1089"


def _ws_call(payload: dict, timeout: float = 20.0) -> dict:
    url = _WS_URL.format(app_id=_app_id())
    try:
        ws = websocket.create_connection(url, timeout=timeout)
        try:
            ws.send(json.dumps(payload))
            response = json.loads(ws.recv())
        finally:
            ws.close()
    except Exception as exc:
        raise MarketDataError(f"Market data request failed: {exc}") from exc

    if response.get("error"):
        raise MarketDataError(response["error"].get("message", "Market data error"))
    return response


def get_candles(symbol: str, timeframe: str, count: int = 200) -> list[dict]:
    """Return up to `count` most recent candles: [{time, open, high, low, close}]."""
    deriv_symbol = SYMBOL_MAP.get(symbol.upper())
    if not deriv_symbol:
        raise MarketDataError(f"Symbol {symbol} is not supported for market data")
    granularity = GRANULARITY.get(timeframe.upper())
    if not granularity:
        raise MarketDataError(f"Timeframe {timeframe} is not supported (use {', '.join(GRANULARITY)})")

    count = max(10, min(count, 5000))
    cache_key = (deriv_symbol, granularity, count)
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and cached[0] > now:
            return cached[1]

    response = _ws_call({
        "ticks_history": deriv_symbol,
        "adjust_start_time": 1,
        "count": count,
        "end": "latest",
        "granularity": granularity,
        "style": "candles",
    })
    raw = response.get("candles") or []
    candles = [
        {
            "time": int(item["epoch"]),
            "open": float(item["open"]),
            "high": float(item["high"]),
            "low": float(item["low"]),
            "close": float(item["close"]),
        }
        for item in raw
    ]
    if not candles:
        raise MarketDataError(f"No candle data returned for {symbol} {timeframe}")

    with _cache_lock:
        _cache[cache_key] = (now + _CACHE_TTL, candles)
    return candles


def get_price(symbol: str) -> dict:
    """Latest price for a symbol (last M1 close)."""
    candles = get_candles(symbol, "M1", 10)
    last = candles[-1]
    previous = candles[0]
    change = last["close"] - previous["close"]
    return {
        "symbol": symbol.upper(),
        "price": last["close"],
        "time": last["time"],
        "change": change,
        "change_percent": (change / previous["close"] * 100) if previous["close"] else 0.0,
    }


def candles_to_prompt_context(candles: list[dict], max_rows: int = 120) -> str:
    """Compact OHLC text block for the AI prompt."""
    rows = candles[-max_rows:]
    lines = ["epoch,open,high,low,close"]
    for candle in rows:
        lines.append(f"{candle['time']},{candle['open']},{candle['high']},{candle['low']},{candle['close']}")
    return "\n".join(lines)
