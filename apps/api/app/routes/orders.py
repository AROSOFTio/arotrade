"""Manual order API routes.
POST /api/orders/preview  - compute sizing, margin, risk warnings
POST /api/orders/execute  - submit or queue a manual market order
"""
from datetime import datetime
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.services import trading_control
from app.services.mt5_bridge.store import get_account_snapshot, get_quote
from app.services.order_execution import (
    ExecutionError,
    execute_manual_order,
    preview_manual_order,
)
router = APIRouter()
def _is_direct_mt5(account: models.BrokerAccount) -> bool:
    return account.broker == "direct-mt5" or account.connection_state == "direct_connected"
def _enum_value(value) -> str:
    return getattr(value, "value", value)
def _direct_quote(account_id: int, symbol: str) -> dict:
    quote = get_quote(account_id, symbol)
    if not quote:
        raise ExecutionError("Direct MT5 bridge has no fresh quote for this symbol. Keep the EA connected on that chart.")
    bid = float(quote.get("bid") or 0)
    ask = float(quote.get("ask") or 0)
    if bid <= 0 or ask <= 0:
        raise ExecutionError("Direct MT5 bridge quote is missing bid/ask prices.")
    return quote
def _direct_observed_price(direction: str, quote: dict) -> float:
    return float(quote.get("ask") if direction == "buy" else quote.get("bid"))
def _assert_direct_execution_allowed(db: Session, user: models.User, account: models.BrokerAccount, volume: float) -> str:
    control = trading_control.get_platform_control(db)
    account_type = _enum_value(account.account_type)
    if account_type == "live":
        reason = trading_control.live_entry_block_reason(control)
        if reason:
            raise ExecutionError(reason)
        if not user.enable_live_trading or not user.accepted_live_disclaimer:
            raise ExecutionError("Live trading requires user opt-in and accepted risk disclosure.")
        max_live_volume = float(getattr(__import__('app.config', fromlist=['settings']).settings, "MAX_LIVE_ORDER_VOLUME", 1.0))
        if volume > max_live_volume:
            raise ExecutionError(f"Volume exceeds live maximum of {max_live_volume} lots.")
        return "live"
    reason = trading_control.broker_demo_block_reason(control)
    if reason:
        raise ExecutionError(reason)
    return "broker_demo"
def _queue_direct_mt5_order(db: Session, user_id: int, body: schemas.ManualOrderExecuteRequest) -> models.Trade:
    account = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.id == body.broker_account_id,
        models.BrokerAccount.user_id == user_id,
        models.BrokerAccount.is_active == True,  # noqa: E712
    ).first()
    if not account or not _is_direct_mt5(account):
        raise ExecutionError("Direct MT5 account is not connected.")
    if body.volume is None:
        raise ExecutionError("Direct MT5 execution currently requires fixed volume. Use preview for MetaApi risk-percent sizing.")
    if body.volume <= 0:
        raise ExecutionError("Volume must be positive.")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise ExecutionError("User not found.")
    execution_mode = _assert_direct_execution_allowed(db, user, account, float(body.volume))
    quote = _direct_quote(account.id, body.symbol)
    observed_price = _direct_observed_price(body.direction, quote)
    snapshot = get_account_snapshot(account.id) or {}
    positions = snapshot.get("positions") if isinstance(snapshot.get("positions"), list) else []
    if len(positions) >= int(user.max_open_trades or 1):
        raise ExecutionError("Max open trades reached for this account snapshot.")
    client_order_id = f"mt5-{uuid4()}"
    command = {
        "command_id": client_order_id,
        "action": "open_trade",
        "symbol": body.symbol.upper(),
        "direction": body.direction,
        "volume": float(body.volume),
        "stop_loss": float(body.stop_loss),
        "take_profit": float(body.take_profit or 0),
        "observed_price": observed_price,
    }
    intent = models.ExecutionIntent(
        user_id=user_id,
        broker_account_id=account.id,
        execution_mode=execution_mode,
        idempotency_key=body.idempotency_key,
        client_order_id=client_order_id,
        requested_volume=float(body.volume),
        requested_price=observed_price,
        equity_at_time=float(snapshot.get("equity") or account.balance or 0),
        request_payload=command,
        status="QUEUED_DIRECT_MT5",
        execution_state="QUEUED",
    )
    db.add(intent)
    db.flush()
    trade = models.Trade(
        user_id=user_id,
        symbol=body.symbol.upper(),
        trade_type=body.direction,
        entry_price=observed_price,
        entry_time=datetime.utcnow(),
        stop_loss=float(body.stop_loss),
        take_profit=float(body.take_profit) if body.take_profit is not None else None,
        volume=float(body.volume),
        status=models.TradeStatus.PENDING,
        mode=models.TradingMode.LIVE if execution_mode == "live" else models.TradingMode.DEMO,
        broker="direct-mt5",
        client_order_id=client_order_id,
        execution_status="queued_direct_mt5",
        submitted_at=datetime.utcnow(),
        broker_account_id=account.id,
        execution_mode=execution_mode,
        provider="direct-mt5",
        broker_symbol=body.symbol.upper(),
        execution_intent_id=intent.id,
        requested_price=observed_price,
        requested_volume=float(body.volume),
        actual_volume=float(body.volume),
        notes="Queued for AroPilot MT5 Expert Advisor execution.",
    )
    db.add(trade)
    db.flush()
    db.add(models.ExecutionAudit(
        user_id=user_id,
        trade_id=trade.id,
        broker="direct-mt5",
        mode=execution_mode,
        outcome="queued",
        reason="Queued for direct MT5 EA execution",
        details=command,
    ))
    db.commit()
    db.refresh(trade)
    return trade
def _preview_direct_mt5_order(db: Session, user_id: int, body: schemas.ManualOrderPreviewRequest) -> schemas.ManualOrderPreviewResponse:
    account = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.id == body.broker_account_id,
        models.BrokerAccount.user_id == user_id,
        models.BrokerAccount.is_active == True,  # noqa: E712
    ).first()
    if not account or not _is_direct_mt5(account):
        raise ExecutionError("Direct MT5 account is not connected.")
    if body.volume is None:
        raise ExecutionError("Direct MT5 preview requires fixed volume because broker-side margin/spec data is supplied by the EA snapshot.")
    quote = _direct_quote(account.id, body.symbol)
    observed_price = _direct_observed_price(body.direction, quote)
    bid = float(quote.get("bid") or 0)
    ask = float(quote.get("ask") or 0)
    snapshot = get_account_snapshot(account.id) or {}
    equity = float(snapshot.get("equity") or account.balance or 0)
    balance = float(snapshot.get("balance") or account.balance or 0)
    risk_amount = abs(observed_price - float(body.stop_loss)) * float(body.volume)
    effective_risk = (risk_amount / equity * 100.0) if equity > 0 else 0.0
    return schemas.ManualOrderPreviewResponse(
        broker_symbol=body.symbol.upper(),
        direction=body.direction,
        bid=bid,
        ask=ask,
        spread=float(quote.get("spread") or 0),
        observed_price=observed_price,
        stop_loss=float(body.stop_loss),
        take_profit=body.take_profit,
        calculated_volume=float(body.volume),
        risk_amount=risk_amount,
        effective_risk_percent=effective_risk,
        required_margin=0.0,
        free_margin_after=float(snapshot.get("free_margin") or 0),
        equity=equity,
        balance=balance,
        account_currency=str(snapshot.get("currency") or account.currency or "USD"),
        quote_time=quote.get("time"),
        quote_age_seconds=None,
        stale_data_warning=False,
        risk_warnings=[] if body.take_profit else ["Take profit is optional, but recommended for direct MT5 execution."],
    )
@router.post("/preview", response_model=schemas.ManualOrderPreviewResponse)
async def preview_order(
    body: schemas.ManualOrderPreviewRequest,
    current_user: dict = Depends(
        __import__('app.auth', fromlist=['get_current_user']).get_current_user
    ),
    db: Session = Depends(get_db),
):
    """Preview a manual market order without submitting it."""
    try:
        account = db.query(models.BrokerAccount).filter(
            models.BrokerAccount.id == body.broker_account_id,
            models.BrokerAccount.user_id == current_user["user_id"],
        ).first()
        if account and _is_direct_mt5(account):
            return _preview_direct_mt5_order(db, current_user["user_id"], body)
        result = preview_manual_order(
            db,
            user_id=current_user["user_id"],
            broker_account_id=body.broker_account_id,
            symbol=body.symbol,
            direction=body.direction,
            stop_loss=body.stop_loss,
            take_profit=body.take_profit,
            volume=body.volume,
            risk_percent=body.risk_percent,
        )
        return result
    except ExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Preview failed: {exc}",
        )
@router.post("/execute", response_model=schemas.TradeResponse)
async def execute_order(
    body: schemas.ManualOrderExecuteRequest,
    current_user: dict = Depends(
        __import__('app.auth', fromlist=['get_current_user']).get_current_user
    ),
    db: Session = Depends(get_db),
):
    """Execute or queue a manual market order through the selected broker integration."""
    try:
        account = db.query(models.BrokerAccount).filter(
            models.BrokerAccount.id == body.broker_account_id,
            models.BrokerAccount.user_id == current_user["user_id"],
        ).first()
        if account and _is_direct_mt5(account):
            return _queue_direct_mt5_order(db, current_user["user_id"], body)
        trade = execute_manual_order(
            db,
            user_id=current_user["user_id"],
            broker_account_id=body.broker_account_id,
            symbol=body.symbol,
            direction=body.direction,
            stop_loss=body.stop_loss,
            take_profit=body.take_profit,
            volume=body.volume,
            risk_percent=body.risk_percent,
            idempotency_key=body.idempotency_key,
        )
        return trade
    except ExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Execution failed: {exc}",
        )
