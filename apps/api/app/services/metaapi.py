"""Thin REST client for MetaApi (metaapi.cloud) MT4/MT5 connectivity.

Uses the provisioning API to register/deploy broker accounts and the regional
client API for market data and order execution. All calls are synchronous
httpx requests with short timeouts; callers translate MetaApiError into HTTP
responses.
"""

from typing import Optional

import httpx

from app.config import settings

PROVISIONING_BASE = "https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai"


class MetaApiError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class MetaApiNotConfigured(MetaApiError):
    def __init__(self):
        super().__init__("METAAPI_TOKEN is not configured", 503)


def _headers() -> dict:
    if not settings.METAAPI_TOKEN:
        raise MetaApiNotConfigured()
    return {"auth-token": settings.METAAPI_TOKEN, "Content-Type": "application/json"}


def _client_base() -> str:
    region = settings.METAAPI_REGION or "london"
    return f"https://mt-client-api-v1.{region}.agiliumtrade.ai"


def _request(method: str, url: str, json_body: Optional[dict] = None, timeout: float = 30.0) -> httpx.Response:
    try:
        response = httpx.request(method, url, headers=_headers(), json=json_body, timeout=timeout)
    except httpx.HTTPError as exc:
        raise MetaApiError(f"MetaApi request failed: {exc}") from exc

    if response.status_code >= 400:
        try:
            detail = response.json().get("message", response.text)
        except Exception:
            detail = response.text
        raise MetaApiError(f"MetaApi error ({response.status_code}): {detail}", response.status_code)
    return response


def create_account(name: str, login: str, password: str, server: str, platform: str = "mt5") -> dict:
    """Register a broker account with MetaApi. Does NOT deploy it (no hourly cost yet)."""
    payload = {
        "name": name,
        "type": "cloud-g2",
        "login": login,
        "password": password,
        "server": server,
        "platform": platform,
        "magic": 0,
        "region": settings.METAAPI_REGION or "london",
        "keywords": ["AroTrade"],
    }
    response = _request("POST", f"{PROVISIONING_BASE}/users/current/accounts", payload, timeout=60.0)
    return response.json()


def account_identifier(account: dict) -> Optional[str]:
    return account.get("id") or account.get("_id")


def get_account(metaapi_account_id: str) -> dict:
    response = _request("GET", f"{PROVISIONING_BASE}/users/current/accounts/{metaapi_account_id}")
    return response.json()


def deploy_account(metaapi_account_id: str) -> None:
    _request("POST", f"{PROVISIONING_BASE}/users/current/accounts/{metaapi_account_id}/deploy")


def undeploy_account(metaapi_account_id: str) -> None:
    _request("POST", f"{PROVISIONING_BASE}/users/current/accounts/{metaapi_account_id}/undeploy")


def remove_account(metaapi_account_id: str) -> None:
    _request("DELETE", f"{PROVISIONING_BASE}/users/current/accounts/{metaapi_account_id}")


def get_account_information(metaapi_account_id: str) -> dict:
    """Balance, equity, currency etc. Requires the account to be deployed and connected."""
    response = _request(
        "GET",
        f"{_client_base()}/users/current/accounts/{metaapi_account_id}/account-information",
        timeout=45.0,
    )
    return response.json()


def get_symbols(metaapi_account_id: str) -> list:
    """Full tradable symbol list from the connected broker."""
    response = _request(
        "GET",
        f"{_client_base()}/users/current/accounts/{metaapi_account_id}/symbols",
        timeout=45.0,
    )
    return response.json()


def get_symbol_price(metaapi_account_id: str, symbol: str) -> dict:
    response = _request(
        "GET",
        f"{_client_base()}/users/current/accounts/{metaapi_account_id}/symbols/{symbol}/current-price",
        timeout=30.0,
    )
    return response.json()


def place_market_order(
    metaapi_account_id: str,
    symbol: str,
    direction: str,
    volume: float,
    stop_loss: float,
    take_profit: Optional[float],
    client_id: str,
    comment: str = "AroTrade signal",
) -> dict:
    """Submit a market order with mandatory stop loss."""
    if direction not in ("buy", "sell"):
        raise MetaApiError("Order direction must be buy or sell", 400)
    if not stop_loss or stop_loss <= 0:
        raise MetaApiError("A stop loss is required for every live order", 400)

    payload = {
        "actionType": "ORDER_TYPE_BUY" if direction == "buy" else "ORDER_TYPE_SELL",
        "symbol": symbol,
        "volume": volume,
        "stopLoss": stop_loss,
        "clientId": client_id,
        "comment": comment[:26],
    }
    if take_profit:
        payload["takeProfit"] = take_profit

    response = _request(
        "POST",
        f"{_client_base()}/users/current/accounts/{metaapi_account_id}/trade",
        payload,
        timeout=60.0,
    )
    return response.json()


def get_positions(metaapi_account_id: str) -> list:
    response = _request(
        "GET",
        f"{_client_base()}/users/current/accounts/{metaapi_account_id}/positions",
        timeout=45.0,
    )
    return response.json()
