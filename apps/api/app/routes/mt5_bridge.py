from __future__ import annotations
from datetime import datetime
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session
from app import models
from app.database import get_db
from app.services.chart_analysis import engine as chart_analysis_engine
from app.services.mt5_bridge.store import (
    get_candles,
    require_bridge_account,
    store_account_snapshot,
    store_candles,
    store_quote,
)


MT5_MAX_SR_LEVELS = 8


def _trim_mt5_json_body(body: bytes) -> bytes:
    return body.rstrip(b"\x00")


class MT5BridgeRoute(APIRoute):
    """Normalize the terminal NUL emitted by MT5's working WebRequest form."""

    def get_route_handler(self):
        original_route_handler = super().get_route_handler()

        async def bridge_route_handler(request: Request):
            if request.method == "POST":
                body = await request.body()
                trimmed = _trim_mt5_json_body(body)
                if trimmed != body:
                    # Starlette caches the body here; normal FastAPI parsing and
                    # validation still run after this bridge-only normalization.
                    request._body = trimmed
            return await original_route_handler(request)

        return bridge_route_handler


router = APIRouter(route_class=MT5BridgeRoute)
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


def _deterministic_chart_objects(account: models.BrokerAccount, symbol: str | None, timeframe: str | None) -> list[dict]:
    if not symbol or not timeframe:
        return []
    candles = get_candles(account.id, symbol, timeframe, 300)
    if len(candles) < 50:
        return []
    try:
        analysis = chart_analysis_engine.analyze_chart(
            symbol=symbol.upper(),
            broker_symbol=symbol.upper(),
            timeframe=timeframe.upper(),
            candles=candles,
            include="support_resistance",
        )
    except Exception:
        return []

    current_price = analysis.market_state.current_price or candles[-1].get("close") or 0
    support = None
    resistance = None
    for finding in analysis.experts[0].findings if analysis.experts else []:
        if finding.price is None:
            continue
        if finding.price < current_price and (support is None or finding.price > support.price):
            support = finding
        if finding.price > current_price and (resistance is None or finding.price < resistance.price):
            resistance = finding

    def _price_of(drawing) -> float:
        for value in (drawing.price_start, drawing.price_end, drawing.price_high, drawing.price_low):
            if isinstance(value, (int, float)) and value > 0:
                return float(value)
        return 0.0

    sr_lines = [
        drawing
        for drawing in analysis.drawings
        if getattr(drawing, "enabled", True)
        and drawing.type == "horizontal_line"
        and (drawing.metadata or {}).get("expert") == "support_resistance"
        and _price_of(drawing) > 0
    ]
    sr_lines = sorted(sr_lines, key=lambda drawing: abs(_price_of(drawing) - float(current_price or 0)))[:MT5_MAX_SR_LEVELS]

    trade_levels = []
    if analysis.signal.action in ("BUY", "SELL"):
        trade_levels = [
            drawing
            for drawing in analysis.drawings
            if getattr(drawing, "enabled", True)
            and drawing.type in {"entry_zone", "stop_loss", "take_profit", "signal_marker"}
        ][:5]

    next_step = "WAIT: no clean trade yet. Watch reaction at nearest support/resistance."
    if analysis.signal.action in ("BUY", "SELL"):
        next_step = (
            f"{analysis.signal.action}: wait for confirmation in the entry zone. "
            f"SL {analysis.signal.stop_loss or '-'} TP {analysis.signal.take_profit_1 or '-'}."
        )
    text_lines = [
        f"AroPilot {symbol.upper()} {timeframe.upper()}",
        next_step,
    ]
    if support:
        text_lines.append(f"Support: {support.price:.2f} ({support.label})")
    if resistance:
        text_lines.append(f"Resistance: {resistance.price:.2f} ({resistance.label})")
    if analysis.experts:
        text_lines.append(f"S/R score: {analysis.experts[0].score}/100")

    text_object = {
        "type": "text_label",
        "id": f"{symbol}:{timeframe}:aropilot-plan",
        "label": "\\n".join(text_lines[:5]),
        "price": current_price,
        "confidence": analysis.experts[0].score if analysis.experts else analysis.signal.confidence,
    }

    objects = [text_object]
    objects.extend(drawing.model_dump(mode="json") for drawing in sr_lines)
    objects.extend(drawing.model_dump(mode="json") for drawing in trade_levels)
    return objects[:14]


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
def _pending_direct_mt5_command(db: Session, account: models.BrokerAccount) -> models.ExecutionIntent | None:
    return db.query(models.ExecutionIntent).filter(
        models.ExecutionIntent.broker_account_id == account.id,
        models.ExecutionIntent.status == "QUEUED_DIRECT_MT5",
    ).order_by(models.ExecutionIntent.created_at.asc()).first()
def _command_payload(intent: models.ExecutionIntent) -> dict:
    payload = intent.request_payload if isinstance(intent.request_payload, dict) else {}
    return {
        "command_id": intent.client_order_id,
        "action": payload.get("action") or "open_trade",
        "symbol": payload.get("symbol"),
        "direction": payload.get("direction"),
        "volume": payload.get("volume"),
        "stop_loss": payload.get("stop_loss"),
        "take_profit": payload.get("take_profit") or 0,
        "position_ticket": payload.get("position_ticket") or payload.get("position_id") or payload.get("broker_position_id"),
    }
def _mark_direct_command_sent(db: Session, intent: models.ExecutionIntent) -> None:
    intent.status = "SENT_TO_MT5"
    intent.execution_state = "SENT"
    trade = db.query(models.Trade).filter(models.Trade.execution_intent_id == intent.id).first()
    if trade:
        trade.execution_status = "sent_to_mt5"
        trade.submitted_at = trade.submitted_at or datetime.utcnow()
    db.commit()
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
    if payload.get("account_type") == "live":
        account.account_type = models.TradingMode.LIVE
    elif payload.get("account_type") == "demo":
        account.account_type = models.TradingMode.DEMO
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
    chart_objects = _deterministic_chart_objects(account, symbol, timeframe)
    if not chart_objects and analysis:
        chart_objects = analysis.get("chart_objects", [])
    pending = _pending_direct_mt5_command(db, account)
    command = _command_payload(pending) if pending else None
    response = {
        "account_id": account.id,
        "trade_execution_enabled": bool(command),
        "auto_trading_enabled": bool(command),
        "risk": {
            "max_risk_percent": 0.25,
            "max_daily_loss_percent": 3.0,
            "max_open_trades": 1,
            "confirmation_required": True,
        },
        "market_summary": analysis,
        "signal": signal,
        "notifications": [],
        "chart_objects": chart_objects,
        "commands": [command] if command else [],
    }
    if command:
        response.update(command)
        _mark_direct_command_sent(db, pending)
    return response
@router.post("/command-result")
async def bridge_command_result(
    payload: dict,
    x_aropilot_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    account_id = int(payload.get("account_id") or 0)
    account = require_bridge_account(db, x_aropilot_key, account_id)
    command_id = str(payload.get("command_id") or "").strip()
    if not command_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="command_id is required")
    intent = db.query(models.ExecutionIntent).filter(
        models.ExecutionIntent.broker_account_id == account.id,
        models.ExecutionIntent.client_order_id == command_id,
    ).first()
    if not intent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="command not found")
    success = bool(payload.get("success"))
    intent.broker_response = payload
    intent.error = None if success else str(payload.get("message") or "MT5 command rejected")
    intent.broker_order_id = str(payload.get("order_ticket") or "") or None
    intent.broker_deal_id = str(payload.get("deal_ticket") or "") or None
    if payload.get("position_ticket"):
        intent.broker_position_id = str(payload.get("position_ticket"))
    intent.status = "FILLED" if success else "REJECTED"
    intent.execution_state = "FILLED" if success else "REJECTED"
    trade = db.query(models.Trade).filter(models.Trade.execution_intent_id == intent.id).first()
    if trade:
        request_payload = intent.request_payload if isinstance(intent.request_payload, dict) else {}
        action = str(request_payload.get("action") or "open_trade")
        trade.broker_order_id = intent.broker_order_id
        trade.broker_deal_id = intent.broker_deal_id
        trade.execution_error = intent.error
        if success:
            if action == "open_trade":
                trade.status = models.TradeStatus.OPEN
                trade.execution_status = "filled"
                trade.filled_at = datetime.utcnow()
                trade.opened_time = trade.filled_at
                trade.actual_fill_price = trade.requested_price
                if intent.broker_position_id:
                    trade.broker_position_id = intent.broker_position_id
            elif action == "modify_position":
                if request_payload.get("stop_loss") is not None:
                    trade.stop_loss = float(request_payload["stop_loss"])
                if request_payload.get("take_profit") is not None:
                    trade.take_profit = float(request_payload["take_profit"])
                trade.execution_status = "protection_modified"
                trade.reconciliation_status = "modified"
            elif action == "close_position":
                trade.status = models.TradeStatus.CLOSED
                trade.execution_status = "closed"
                trade.exit_time = datetime.utcnow()
                trade.closed_time = trade.exit_time
            elif action == "partial_close":
                trade.execution_status = "partially_closed"
                trade.reconciliation_status = "partially_reconciled"
                if request_payload.get("remaining_volume") is not None:
                    trade.actual_volume = float(request_payload["remaining_volume"])
        else:
            if action == "open_trade":
                trade.status = models.TradeStatus.CANCELLED
            trade.execution_status = "rejected"
    db.commit()
    return {"status": "recorded", "command_id": command_id, "success": success}
