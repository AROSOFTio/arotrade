"""Unified MetaApi market-data and execution gateway.

This is the SINGLE source of truth for all market data when the active
trading profile is an MT4/MT5 account connected via MetaApi.

Responsibilities:
  - Retrieve broker-specific symbol lists and specifications
  - Fetch current bid/ask quotes
  - Fetch historical candles
  - Submit market orders (with mandatory stop-loss)
  - Retrieve open positions and orders
  - Close broker positions
  - Modify stop-loss / take-profit on open positions
  - Retrieve account information (balance, equity, margin, free margin)

Do NOT use this file for Deriv-specific operations.
Do NOT call the old marketdata.py for MT5 workflows.

The `MetaApiError` exception is intentionally identical to the one in the
older metaapi.py module so existing callers work without changes.
"""

from __future__ import annotations

import logging
from datetime import datetime, UTC
from typing import Optional
from urllib.parse import quote

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

PROVISIONING_BASE = "https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai"


class MetaApiError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class MetaApiNotConfigured(MetaApiError):
    def __init__(self):
        super().__init__("METAAPI_TOKEN is not configured", 503)


class QuoteStaleError(MetaApiError):
    """Raised when a quote is older than QUOTE_STALE_AFTER_SECONDS."""
    def __init__(self, age_seconds: float):
        super().__init__(
            f"Broker quote is {age_seconds:.0f}s old (limit {settings.QUOTE_STALE_AFTER_SECONDS}s). "
            "Execution blocked ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â do not trade on stale prices.",
            503,
        )


class SymbolNotFoundError(MetaApiError):
    """Raised when a symbol cannot be resolved for the given broker account."""
    def __init__(self, canonical: str, account_id: str):
        super().__init__(
            f"Symbol '{canonical}' cannot be resolved for broker account {account_id}. "
            "Check the broker symbol mapping.",
            404,
        )


def _headers() -> dict:
    if not settings.METAAPI_TOKEN:
        raise MetaApiNotConfigured()
    return {"auth-token": settings.METAAPI_TOKEN, "Content-Type": "application/json"}


def _client_base() -> str:
    region = settings.METAAPI_REGION or "london"
    return f"https://mt-client-api-v1.{region}.agiliumtrade.ai"


def _market_data_base() -> str:
    region = settings.METAAPI_REGION or "london"
    return f"https://mt-market-data-client-api-v1.{region}.agiliumtrade.ai"


def _request(
    method: str,
    url: str,
    json_body: Optional[dict] = None,
    timeout: float = 30.0,
) -> httpx.Response:
    try:
        response = httpx.request(
            method, url, headers=_headers(), json=json_body, timeout=timeout
        )
    except httpx.HTTPError as exc:
        raise MetaApiError(f"MetaApi network error: {exc}") from exc

    if response.status_code >= 400:
        try:
            detail = response.json().get("message", response.text)
        except Exception:
            detail = response.text
        raise MetaApiError(
            f"MetaApi error ({response.status_code}): {detail}",
            response.status_code,
        )
    return response


# ---------------------------------------------------------------------------
# Account provisioning (registration / deploy / undeploy)
# ---------------------------------------------------------------------------

def create_account(
    name: str,
    login: str,
    password: str,
    server: str,
    platform: str = "mt5",
    account_type: str = "cloud-g2",
) -> dict:
    """Register a broker account with MetaApi.  Does NOT deploy it yet."""
    payload = {
        "name": name,
        "type": account_type,
        "login": login,
        "password": password,
        "server": server,
        "platform": platform,
        "magic": 0,
        "region": settings.METAAPI_REGION or "london",
        "keywords": ["AroTrade"],
    }
    response = _request(
        "POST",
        f"{PROVISIONING_BASE}/users/current/accounts",
        payload,
        timeout=60.0,
    )
    return response.json()


def get_account(metaapi_account_id: str) -> dict:
    response = _request(
        "GET",
        f"{PROVISIONING_BASE}/users/current/accounts/{metaapi_account_id}",
    )
    return response.json()


def deploy_account(metaapi_account_id: str) -> None:
    _request("POST", f"{PROVISIONING_BASE}/users/current/accounts/{metaapi_account_id}/deploy")


def undeploy_account(metaapi_account_id: str) -> None:
    _request("POST", f"{PROVISIONING_BASE}/users/current/accounts/{metaapi_account_id}/undeploy")


def remove_account(metaapi_account_id: str) -> None:
    _request("DELETE", f"{PROVISIONING_BASE}/users/current/accounts/{metaapi_account_id}")


def account_identifier(account: dict) -> Optional[str]:
    return account.get("id") or account.get("_id")


# ---------------------------------------------------------------------------
# Account information
# ---------------------------------------------------------------------------

def get_account_information(metaapi_account_id: str) -> dict:
    """Balance, equity, margin, free margin.  Account must be deployed."""
    response = _request(
        "GET",
        f"{_client_base()}/users/current/accounts/{metaapi_account_id}/account-information",
        timeout=45.0,
    )
    return response.json()


# ---------------------------------------------------------------------------
# Symbol catalogue and specifications
# ---------------------------------------------------------------------------

def get_symbols(metaapi_account_id: str) -> list:
    """Full tradable symbol list from the connected broker."""
    response = _request(
        "GET",
        f"{_client_base()}/users/current/accounts/{metaapi_account_id}/symbols",
        timeout=60.0,
    )
    return response.json()


def get_symbol_specification(metaapi_account_id: str, symbol: str) -> dict:
    """Full symbol specification: digits, point, tick size/value, volume limits, etc."""
    response = _request(
        "GET",
        f"{_client_base()}/users/current/accounts/{metaapi_account_id}/symbols/{symbol}/specification",
        timeout=30.0,
    )
    return response.json()


# ---------------------------------------------------------------------------
# Quotes
# ---------------------------------------------------------------------------

def get_symbol_price(
    metaapi_account_id: str,
    symbol: str,
    *,
    require_fresh: bool = True,
) -> dict:
    """
    Current bid/ask for a broker symbol.

    When require_fresh=True (the default), raises QuoteStaleError when the
    quote timestamp is older than settings.QUOTE_STALE_AFTER_SECONDS.
    Always use require_fresh=True before any execution decision.
    """
    response = _request(
        "GET",
        f"{_client_base()}/users/current/accounts/{metaapi_account_id}/symbols/{symbol}/current-price",
        timeout=30.0,
    )
    quote = response.json()

    if require_fresh:
        quote_time_str = quote.get("time") or quote.get("brokerTime")
        if quote_time_str:
            try:
                if isinstance(quote_time_str, str):
                    # MetaApi returns ISO strings; strip Z and parse
                    quote_time = datetime.fromisoformat(quote_time_str.replace("Z", "+00:00"))
                    age = (datetime.now(UTC) - quote_time).total_seconds()
                    if age > settings.QUOTE_STALE_AFTER_SECONDS:
                        raise QuoteStaleError(age)
            except QuoteStaleError:
                raise
            except Exception:
                pass  # Cannot parse time ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â let execution service decide

    return quote


def extract_observed_price(quote: dict, direction: str) -> float:
    """
    Extract the correct execution price from a broker quote.
    BUY orders execute at ASK.  SELL orders execute at BID.
    Never use mid-price for execution validation.
    """
    bid = quote.get("bid") or quote.get("brokerBid")
    ask = quote.get("ask") or quote.get("brokerAsk")
    price = ask if direction.lower() == "buy" else bid
    price = price or quote.get("price") or quote.get("last") or quote.get("close")
    try:
        return float(price)
    except (TypeError, ValueError):
        return 0.0



def calculate_margin(
    metaapi_account_id: str,
    symbol: str,
    direction: str,
    volume: float,
    entry_price: float,
) -> dict:
    """Ask MetaApi/broker to calculate required margin for the exact order."""
    direction_lower = direction.lower()
    if direction_lower not in ("buy", "sell"):
        raise MetaApiError("Order direction must be 'buy' or 'sell'", 400)
    payload = {
        "symbol": symbol,
        "type": "ORDER_TYPE_BUY" if direction_lower == "buy" else "ORDER_TYPE_SELL",
        "volume": round(volume, 8),
        "openPrice": entry_price,
    }
    response = _request(
        "POST",
        f"{_client_base()}/users/current/accounts/{metaapi_account_id}/calculate-margin",
        payload,
        timeout=45.0,
    )
    result = response.json()
    if not isinstance(result, dict):
        raise MetaApiError("Broker margin calculation returned an invalid response", 502)
    margin = result.get("margin") or result.get("requiredMargin") or result.get("required_margin")
    try:
        parsed = float(margin)
    except (TypeError, ValueError) as exc:
        raise MetaApiError("Broker margin calculation did not return required margin", 502) from exc
    result["requiredMargin"] = parsed
    return result
# ---------------------------------------------------------------------------
# Candles
# ---------------------------------------------------------------------------

def get_candles(
    metaapi_account_id: str,
    symbol: str,
    timeframe: str,
    count: int = 200,
) -> list[dict]:
    """
    Historical OHLCV candles from the broker account.

    timeframe is the MetaApi format: '1m', '5m', '15m', '30m', '1h', '4h', '1d'.
    Returns list of dicts: {time, open, high, low, close, volume, ...}
    """
    response = _request(
        "GET",
        (
            f"{_market_data_base()}/users/current/accounts/{metaapi_account_id}"
            f"/historical-market-data/symbols/{quote(symbol, safe='')}"
            f"/timeframes/{quote(timeframe, safe='')}/candles?limit={count}"
        ),
        timeout=60.0,
    )
    raw = response.json()
    if isinstance(raw, list):
        return raw[-count:]
    return []


# MetaApi timeframe strings differ from common notation
TIMEFRAME_MAP: dict[str, str] = {
    "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
    "H1": "1h", "H4": "4h", "D1": "1d", "W1": "1w",
}


def normalize_timeframe(tf: str) -> str:
    """Convert internal timeframe (H1, M15, ...) to MetaApi format (1h, 15m, ...)."""
    return TIMEFRAME_MAP.get(tf.upper(), tf.lower())


def candles_to_prompt_context(candles: list[dict], max_rows: int = 120) -> str:
    """Compact OHLC text block for AI prompts."""
    rows = candles[-max_rows:]
    lines = ["time,open,high,low,close"]
    for candle in rows:
        t = candle.get("time") or candle.get("brokerTime") or ""
        o = candle.get("open", 0)
        h = candle.get("high", 0)
        lo = candle.get("low", 0)
        c = candle.get("close", 0)
        lines.append(f"{t},{o},{h},{lo},{c}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Open positions
# ---------------------------------------------------------------------------

def get_positions(metaapi_account_id: str) -> list:
    """All currently open positions."""
    response = _request(
        "GET",
        f"{_client_base()}/users/current/accounts/{metaapi_account_id}/positions",
        timeout=45.0,
    )
    return response.json()


def get_orders(metaapi_account_id: str) -> list:
    """All pending orders."""
    response = _request(
        "GET",
        f"{_client_base()}/users/current/accounts/{metaapi_account_id}/orders",
        timeout=45.0,
    )
    return response.json()


def get_history_orders(
    metaapi_account_id: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> list:
    """Historical orders/deals for reconciliation."""
    params = {}
    if start_time:
        params["startTime"] = start_time
    if end_time:
        params["endTime"] = end_time
    url = f"{_client_base()}/users/current/accounts/{metaapi_account_id}/history-orders/time/{start_time or '2000-01-01T00:00:00.000Z'}/{end_time or '2099-12-31T23:59:59.999Z'}"
    try:
        response = _request("GET", url, timeout=60.0)
        return response.json()
    except Exception as exc:
        logger.warning("Failed to fetch history orders: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Order execution
# ---------------------------------------------------------------------------

SUCCESS_TRADE_STRING_CODES = {
    "TRADE_RETCODE_PLACED",
    "TRADE_RETCODE_DONE",
    "TRADE_RETCODE_DONE_PARTIAL",
    "TRADE_RETCODE_NO_CHANGES",
}

SUCCESS_TRADE_NUMERIC_CODES = {10008, 10009, 10010, 10025}


def validate_trade_response(
    response: dict,
    *,
    require_trade_reference: bool = True,
) -> dict:
    """Accept only explicit MT5 success trade responses."""
    if not isinstance(response, dict):
        raise MetaApiError("Broker returned an invalid trade response", 502)

    string_code = response.get("stringCode")
    numeric_code = response.get("numericCode")
    message = response.get("message") or response.get("error") or "No broker message"

    if string_code and string_code not in SUCCESS_TRADE_STRING_CODES:
        raise MetaApiError(f"Broker rejected trade ({string_code}): {message}", 400)

    if numeric_code is not None:
        try:
            parsed_code = int(numeric_code)
        except (TypeError, ValueError) as exc:
            raise MetaApiError(f"Broker returned an invalid numeric code: {numeric_code}", 502) from exc
        if parsed_code not in SUCCESS_TRADE_NUMERIC_CODES:
            raise MetaApiError(f"Broker rejected trade ({parsed_code}): {message}", 400)

    if string_code is None and numeric_code is None:
        raise MetaApiError("Broker response did not include an MT5 success code", 502)

    if require_trade_reference and not (
        response.get("orderId") or response.get("positionId") or response.get("dealId")
    ):
        raise MetaApiError("Broker accepted the request but returned no order, deal, or position reference", 502)

    return response


def place_market_order(
    metaapi_account_id: str,
    symbol: str,
    direction: str,
    volume: float,
    stop_loss: float,
    take_profit: Optional[float] = None,
    client_id: str = "",
    comment: str = "AroTrade signal",
) -> dict:
    """
    Submit a market order.

    SAFETY RULES (enforced here, not just in the route):
      - stop_loss is REQUIRED ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â no exceptions
      - direction must be 'buy' or 'sell'
      - symbol is the BROKER symbol (not canonical)
    """
    direction_lower = direction.lower()
    if direction_lower not in ("buy", "sell"):
        raise MetaApiError("Order direction must be 'buy' or 'sell'", 400)
    if not stop_loss or stop_loss <= 0:
        raise MetaApiError("A stop loss is required for every order", 400)
    if volume <= 0:
        raise MetaApiError("Volume must be positive", 400)

    payload: dict = {
        "actionType": "ORDER_TYPE_BUY" if direction_lower == "buy" else "ORDER_TYPE_SELL",
        "symbol": symbol,
        "volume": round(volume, 8),
        "stopLoss": stop_loss,
        "comment": comment[:26],
    }
    if take_profit:
        payload["takeProfit"] = take_profit
    if client_id:
        payload["clientId"] = client_id

    response = _request(
        "POST",
        f"{_client_base()}/users/current/accounts/{metaapi_account_id}/trade",
        payload,
        timeout=60.0,
    )
    return validate_trade_response(response.json(), require_trade_reference=True)


def close_position(
    metaapi_account_id: str,
    position_id: str,
    volume: Optional[float] = None,
) -> dict:
    """
    Close an open broker position.

    If volume is None, the full position is closed.
    If volume is specified and the broker supports it, a partial close is sent.

    CRITICAL: Always call this for broker trades. Never close a position
    only in the local database.
    """
    if volume is not None:
        payload = {"actionType": "POSITION_PARTIAL", "positionId": position_id, "volume": volume}
    else:
        payload = {"actionType": "POSITION_CLOSE_ID", "positionId": position_id}

    response = _request(
        "POST",
        f"{_client_base()}/users/current/accounts/{metaapi_account_id}/trade",
        payload,
        timeout=60.0,
    )
    return validate_trade_response(response.json(), require_trade_reference=False)


def modify_position(
    metaapi_account_id: str,
    position_id: str,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
) -> dict:
    """Modify stop-loss and/or take-profit on an open position."""
    if stop_loss is None and take_profit is None:
        raise MetaApiError("At least one of stop_loss or take_profit must be provided", 400)

    payload: dict = {"actionType": "POSITION_MODIFY", "positionId": position_id}
    if stop_loss is not None:
        payload["stopLoss"] = stop_loss
    if take_profit is not None:
        payload["takeProfit"] = take_profit

    response = _request(
        "POST",
        f"{_client_base()}/users/current/accounts/{metaapi_account_id}/trade",
        payload,
        timeout=60.0,
    )
    return validate_trade_response(response.json(), require_trade_reference=False)
