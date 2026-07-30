from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.services.mt5_bridge.store import (
    get_candles,
    require_bridge_account,
    store_account_snapshot,
    store_candles,
    store_quote,
)

router = APIRouter()



def _to_float(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _analysis_to_chart_objects(analysis: models.AIAnalysis) -> list[dict]:
    objects: list[dict] = []
    levels = [
        ("entry_min", "Entry min", analysis.entry_min, "entry"),
        ("entry_max", "Entry max", analysis.entry_max, "entry"),
        ("stop_loss", "Stop loss", analysis.stop_loss, "stop_loss"),
        ("take_profit_1", "Take profit 1", analysis.take_profit_1, "take_profit"),
        ("take_profit_2", "Take profit 2", analysis.take_profit_2, "take_profit"),
        ("take_profit_3", "Take profit 3", analysis.take_profit_3, "take_profit"),
    ]
    for key, label, price, role in levels:
        price_value = _to_float(price)
        if price_value and price_value > 0:
            objects.append({"type": "horizontal_line", "name": key, "label": label, "price": price_value, "role": role})

    entry = _to_float(analysis.entry_min) or _to_float(analysis.entry_max)
    if analysis.signal in ("buy", "sell") and entry and entry > 0:
        objects.append({"type": "arrow", "name": f"{analysis.signal}_signal", "direction": analysis.signal, "price": entry})
    return objects


def _latest_signal_command(db: Session, account: models.BrokerAccount) -> dict | None:
    signal = db.query(models.Signal).filter(
        models.Signal.user_id == account.user_id,
        models.Signal.broker_account_id == account.id,
        models.Signal.status.in_([models.SignalStatus.PENDING, models.SignalStatus.APPROVED]),
    ).order_by(models.Signal.created_at.desc()).first()
    if not signal:
        return None
    return {
        "id": signal.id,
        "symbol": signal.broker_symbol or signal.symbol,
        "timeframe": signal.timeframe,
        "direction": signal.signal_type,
        "entry_min": signal.entry_min,
        "entry_max": signal.entry_max,
        "stop_loss": signal.stop_loss,
        "take_profit_1": signal.take_profit_1,
        "take_profit_2": signal.take_profit_2,
        "take_profit_3": signal.take_profit_3,
        "confidence": signal.confidence,
        "status": getattr(signal.status, "value", signal.status),
        "notes": signal.notes,
    }


def _latest_analysis_command(db: Session, account: models.BrokerAccount, symbol: str | None, timeframe: str | None) -> dict | None:
    query = db.query(models.AIAnalysis).filter(models.AIAnalysis.user_id == account.user_id)
    if symbol:
        query = query.filter(models.AIAnalysis.symbol == symbol.upper())
    if timeframe:
        query = query.filter(models.AIAnalysis.timeframe == timeframe.upper())
    analysis = query.order_by(models.AIAnalysis.created_at.desc()).first()
    if not analysis:
        return None
    return {
        "id": analysis.id,
        "symbol": analysis.symbol,
        "timeframe": analysis.timeframe,
        "bias": analysis.bias,
        "signal": analysis.signal,
        "confidence": analysis.confidence,
        "entry_min": analysis.entry_min,
        "entry_max": analysis.entry_max,
        "stop_loss": analysis.stop_loss,
        "take_profit_1": analysis.take_profit_1,
        "take_profit_2": analysis.take_profit_2,
        "take_profit_3": analysis.take_profit_3,
        "risk_reward": analysis.risk_reward,
        "reasoning": analysis.reasoning or [],
        "invalidation": analysis.invalidation,
        "risk_warning": analysis.risk_warning,
        "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
        "chart_objects": _analysis_to_chart_objects(analysis),
    }


@router.post("/heartbeat")
async def bridge_heartbeat(
    payload: dict,
    x_aropilot_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    account_id = int(payload.get("account_id") or 0)
    if account_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="account_id is required")
    account = require_bridge_account(db, x_aropilot_key, account_id)
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
    store_account_snapshot(account.id, payload)
    db.commit()
    return {"status": "connected", "account_id": account.id, "commands_enabled": True}


@router.post("/quote")
async def bridge_quote(
    payload: dict,
    x_aropilot_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    account_id = int(payload.get("account_id") or 0)
    account = require_bridge_account(db, x_aropilot_key, account_id)
    store_quote(account.id, payload)
    return {"status": "ok"}


@router.post("/candles")
async def bridge_candles(
    payload: dict,
    x_aropilot_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    account_id = int(payload.get("account_id") or 0)
    account = require_bridge_account(db, x_aropilot_key, account_id)
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
    db: Session = Depends(get_db),
):
    account = require_bridge_account(db, x_aropilot_key, account_id)
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
    symbol: str | None = None,
    timeframe: str | None = None,
    x_aropilot_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    account = require_bridge_account(db, x_aropilot_key, account_id)
    signal = _latest_signal_command(db, account)
    analysis = _latest_analysis_command(db, account, symbol, timeframe)
    return {
        "account_id": account.id,
        "trade_execution_enabled": False,
        "auto_trading_enabled": False,
        "risk": {
            "max_risk_percent": 0.25,
            "max_daily_loss_percent": 3.0,
            "max_open_trades": 1,
            "confirmation_required": True,
        },
        "market_summary": analysis,
        "signal": signal,
        "notifications": [],
        "chart_objects": analysis.get("chart_objects", []) if analysis else [],
        "commands": [],
    }