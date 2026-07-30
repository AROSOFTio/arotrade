from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.mt5_bridge.store import get_candles, require_bridge_account, store_candles, store_quote

router = APIRouter()


def bridge_key(x_aropilot_key: str | None, x_arotrader_key: str | None) -> str | None:
    return x_aropilot_key or x_arotrader_key


@router.post("/heartbeat")
async def bridge_heartbeat(
    payload: dict,
    x_aropilot_key: str | None = Header(default=None),
    x_arotrader_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    account_id = int(payload.get("account_id") or 0)
    if account_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="account_id is required")
    account = require_bridge_account(db, bridge_key(x_aropilot_key, x_arotrader_key), account_id)
    account.connection_state = "direct_connected"
    account.broker = "direct-mt5"
    account.platform = "mt5"
    if payload.get("login"):
        account.account_id = str(payload["login"])
    if payload.get("server"):
        account.server = str(payload["server"])
    if payload.get("balance") is not None:
        account.balance = float(payload.get("balance") or 0)
    if payload.get("currency"):
        account.currency = str(payload["currency"])[:3].upper()
    db.commit()
    return {"status": "connected", "account_id": account.id, "commands_enabled": False}


@router.post("/quote")
async def bridge_quote(
    payload: dict,
    x_aropilot_key: str | None = Header(default=None),
    x_arotrader_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    account_id = int(payload.get("account_id") or 0)
    account = require_bridge_account(db, bridge_key(x_aropilot_key, x_arotrader_key), account_id)
    store_quote(account.id, payload)
    return {"status": "ok"}


@router.post("/candles")
async def bridge_candles(
    payload: dict,
    x_aropilot_key: str | None = Header(default=None),
    x_arotrader_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    account_id = int(payload.get("account_id") or 0)
    account = require_bridge_account(db, bridge_key(x_aropilot_key, x_arotrader_key), account_id)
    symbol = str(payload.get("symbol") or "").upper().strip()
    timeframe = str(payload.get("timeframe") or "").upper().strip()
    candles = payload.get("candles") or []
    if not symbol or not timeframe or not isinstance(candles, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="symbol, timeframe and candles are required")
    stored = store_candles(account.id, symbol, timeframe, candles)
    return {"status": "ok", "stored": len(stored)}


@router.get("/candles")
async def read_bridge_candles(
    account_id: int,
    symbol: str,
    timeframe: str = "H1",
    count: int = Query(240, ge=1, le=1000),
    x_aropilot_key: str | None = Header(default=None),
    x_arotrader_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    account = require_bridge_account(db, bridge_key(x_aropilot_key, x_arotrader_key), account_id)
    return {
        "provider": "direct-mt5",
        "account_id": account.id,
        "symbol": symbol.upper(),
        "timeframe": timeframe.upper(),
        "candles": get_candles(account.id, symbol, timeframe, count),
    }


@router.get("/commands")
async def bridge_commands(
    account_id: int,
    x_aropilot_key: str | None = Header(default=None),
    x_arotrader_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    account = require_bridge_account(db, bridge_key(x_aropilot_key, x_arotrader_key), account_id)
    return {"account_id": account.id, "trade_execution_enabled": False, "commands": []}