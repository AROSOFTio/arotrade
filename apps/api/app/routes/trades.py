from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from uuid import uuid4
from app import models, schemas
from app.database import get_db
from app.config import settings
from app.services.mt5_bridge.store import get_account_snapshot

router = APIRouter()


def _is_direct_mt5(account: models.BrokerAccount | None) -> bool:
    return bool(account and (account.broker == "direct-mt5" or account.connection_state == "direct_connected"))


def _position_ticket_from_snapshot(account_id: int, trade: models.Trade) -> str | None:
    snapshot = get_account_snapshot(account_id) or {}
    positions = snapshot.get("positions") if isinstance(snapshot.get("positions"), list) else []
    for position in positions:
        if not isinstance(position, dict):
            continue
        if str(position.get("ticket") or "") in {str(trade.broker_position_id or ""), str(trade.broker_order_id or "")}:
            return str(position.get("ticket"))
    matching = [
        position for position in positions
        if isinstance(position, dict)
        and str(position.get("symbol") or "").upper() == str(trade.broker_symbol or trade.symbol).upper()
        and str(position.get("type") or "").lower() == str(trade.trade_type).lower()
    ]
    if len(matching) == 1:
        return str(matching[0].get("ticket"))
    return str(trade.broker_position_id or trade.broker_order_id or "") or None


def _queue_direct_position_command(
    db: Session,
    *,
    trade: models.Trade,
    account: models.BrokerAccount,
    action: str,
    payload: dict,
    execution_status: str,
) -> models.Trade:
    client_order_id = f"mt5-{uuid4()}"
    command = {
        "command_id": client_order_id,
        "action": action,
        "symbol": (trade.broker_symbol or trade.symbol).upper(),
        **payload,
    }
    intent = models.ExecutionIntent(
        user_id=trade.user_id,
        signal_id=None,
        broker_account_id=account.id,
        execution_mode=trade.execution_mode or ("live" if getattr(account.account_type, "value", account.account_type) == "live" else "broker_demo"),
        idempotency_key=client_order_id,
        client_order_id=client_order_id,
        requested_volume=payload.get("volume"),
        requested_price=trade.entry_price,
        request_payload=command,
        status="QUEUED_DIRECT_MT5",
        execution_state="QUEUED",
    )
    db.add(intent)
    db.flush()
    trade.execution_intent_id = intent.id
    trade.execution_status = execution_status
    trade.execution_error = None
    trade.reconciliation_status = "pending"
    db.add(models.ExecutionAudit(
        user_id=trade.user_id,
        trade_id=trade.id,
        broker="direct-mt5",
        mode=trade.execution_mode or "broker_demo",
        outcome="queued",
        reason=f"Queued direct MT5 {action}",
        details=command,
    ))
    db.commit()
    db.refresh(trade)
    return trade


@router.post("/execute", response_model=schemas.TradeResponse)
async def execute_trade(
    trade_data: schemas.TradeExecute,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Deprecated direct execution route. Use /api/orders/execute."""
    # Get user
    user = db.query(models.User).filter(models.User.id == current_user["user_id"]).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Deprecated endpoint. Use POST /api/orders/execute for MetaApi manual orders."
    )


@router.get("", response_model=list[schemas.TradeResponse])
async def list_trades(
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 50
):
    """List user's trades."""
    trades = db.query(models.Trade).filter(
        models.Trade.user_id == current_user["user_id"]
    ).offset(skip).limit(limit).all()

    return trades


@router.get("/{trade_id}", response_model=schemas.TradeResponse)
async def get_trade(
    trade_id: int,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Get specific trade."""
    trade = db.query(models.Trade).filter(
        models.Trade.id == trade_id,
        models.Trade.user_id == current_user["user_id"]
    ).first()

    if not trade:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trade not found"
        )

    return trade


@router.post("/{trade_id}/close")
async def close_trade(
    trade_id: int,
    request: schemas.PositionCloseRequest = None,
    exit_price: float = None,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Close an open trade (either paper or real broker trade)."""
    trade = db.query(models.Trade).filter(
        models.Trade.id == trade_id,
        models.Trade.user_id == current_user["user_id"]
    ).first()

    if not trade:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trade not found"
        )

    if trade.status != models.TradeStatus.OPEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Trade is not open"
        )

    # 1. Real Broker Execution Mode (broker_demo / live)
    if trade.execution_mode in ("broker_demo", "live"):
        account = db.query(models.BrokerAccount).filter(
            models.BrokerAccount.id == trade.broker_account_id
        ).first()
        if _is_direct_mt5(account):
            position_ticket = _position_ticket_from_snapshot(account.id, trade)
            if not position_ticket:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No matching MT5 position ticket found in the EA snapshot")
            return _queue_direct_position_command(
                db,
                trade=trade,
                account=account,
                action="close_position",
                payload={"position_ticket": position_ticket},
                execution_status="queued_direct_mt5_close",
            )
        if not account or not account.metaapi_account_id:
            raise HTTPException(status_code=400, detail="Broker account mapping missing")

        from app.services import metaapi_gateway as metaapi
        from app.services.execution import _find_confirmed_position
        try:
            position_id = trade.broker_position_id
            if not position_id or (
                trade.broker_order_id and str(position_id) == str(trade.broker_order_id)
            ):
                confirmed = _find_confirmed_position(
                    account,
                    client_order_id=trade.client_order_id or "",
                    comment=f"AT-{trade.signal_id}" if trade.signal_id else (trade.client_order_id or ""),
                )
                if confirmed:
                    trade.broker_order_id = confirmed[0] or trade.broker_order_id
                    trade.broker_position_id = confirmed[1]
                    trade.broker_deal_id = confirmed[2] or trade.broker_deal_id
                    position_id = trade.broker_position_id
                    db.commit()

            if not position_id or (
                trade.broker_order_id and str(position_id) == str(trade.broker_order_id)
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "This broker trade does not have a confirmed MT5 position ID yet. "
                        "Refresh positions or wait for reconciliation before closing it here."
                    ),
                )

            partial_vol = request.volume if request else None
            res = metaapi.close_position(account.metaapi_account_id, position_id, volume=partial_vol)

            # Mark as reconciliation_pending — reconciler will confirm fill details
            trade.reconciliation_status = "reconciliation_pending"
            trade.execution_status = "closing"
            if partial_vol is None:
                trade.status = models.TradeStatus.CLOSED
                trade.exit_time = datetime.utcnow()
                fill_exit = float(res.get("price") or res.get("closePrice") or 0.0)
                trade.exit_price = fill_exit if fill_exit > 0 else None

            db.commit()
            db.refresh(trade)
            return trade
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to close MT5 position: {exc}")

    # 2. Simulated Mode (paper)
    if exit_price is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="exit_price is required for paper trades")

    if trade.trade_type == "buy":
        profit_loss = (exit_price - trade.entry_price) * trade.volume
    else:
        profit_loss = (trade.entry_price - exit_price) * trade.volume

    profit_loss_percent = (profit_loss / (trade.entry_price * trade.volume)) * 100 if trade.entry_price else 0

    trade.exit_price = exit_price
    trade.exit_time = datetime.utcnow()
    trade.profit_loss = profit_loss
    trade.profit_loss_percent = profit_loss_percent
    trade.status = models.TradeStatus.CLOSED

    db.commit()
    db.refresh(trade)

    return trade


@router.patch("/{trade_id}/protection", response_model=schemas.TradeResponse)
async def modify_trade_protection(
    trade_id: int,
    body: schemas.PositionProtectionUpdate,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Modify stop-loss and/or take-profit on an open broker trade."""
    trade = db.query(models.Trade).filter(
        models.Trade.id == trade_id,
        models.Trade.user_id == current_user["user_id"]
    ).first()

    if not trade:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")
    if trade.status != models.TradeStatus.OPEN:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Trade is not open")

    if trade.execution_mode in ("broker_demo", "live"):
        account = db.query(models.BrokerAccount).filter(
            models.BrokerAccount.id == trade.broker_account_id
        ).first()
        if _is_direct_mt5(account):
            position_ticket = _position_ticket_from_snapshot(account.id, trade)
            if not position_ticket:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No matching MT5 position ticket found in the EA snapshot")
            return _queue_direct_position_command(
                db,
                trade=trade,
                account=account,
                action="modify_position",
                payload={
                    "position_ticket": position_ticket,
                    "stop_loss": body.stop_loss if body.stop_loss is not None else trade.stop_loss,
                    "take_profit": body.take_profit if body.take_profit is not None else trade.take_profit,
                },
                execution_status="queued_direct_mt5_modify",
            )
        if not account or not account.metaapi_account_id:
            raise HTTPException(status_code=400, detail="Broker account not connected")
        if not trade.broker_position_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No confirmed broker position ID")

        from app.services import metaapi_gateway as metaapi
        try:
            metaapi.modify_position(
                account.metaapi_account_id,
                trade.broker_position_id,
                stop_loss=body.stop_loss,
                take_profit=body.take_profit,
            )
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Broker rejected modification: {exc}")

    if body.stop_loss is not None:
        trade.stop_loss = body.stop_loss
    if body.take_profit is not None:
        trade.take_profit = body.take_profit

    db.commit()
    db.refresh(trade)
    return trade


@router.post("/{trade_id}/partial-close", response_model=schemas.TradeResponse)
async def partial_close_trade(
    trade_id: int,
    body: schemas.PositionCloseRequest,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Partially close a broker trade."""
    if not body.volume:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="volume is required for partial close")

    trade = db.query(models.Trade).filter(
        models.Trade.id == trade_id,
        models.Trade.user_id == current_user["user_id"]
    ).first()
    if not trade:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")
    if trade.status != models.TradeStatus.OPEN:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Trade is not open")
    if trade.execution_mode not in ("broker_demo", "live"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Partial close is only supported for broker trades")
    if not trade.broker_position_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No confirmed broker position ID")

    account = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.id == trade.broker_account_id
    ).first()
    if _is_direct_mt5(account):
        position_ticket = _position_ticket_from_snapshot(account.id, trade)
        if not position_ticket:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No matching MT5 position ticket found in the EA snapshot")
        current_volume = float(trade.actual_volume or trade.volume or 0)
        remaining = max(0.0, current_volume - float(body.volume))
        return _queue_direct_position_command(
            db,
            trade=trade,
            account=account,
            action="partial_close",
            payload={"position_ticket": position_ticket, "volume": float(body.volume), "remaining_volume": remaining},
            execution_status="queued_direct_mt5_partial_close",
        )
    if not account or not account.metaapi_account_id:
        raise HTTPException(status_code=400, detail="Broker account not connected")

    from app.services import metaapi_gateway as metaapi
    try:
        metaapi.close_position(account.metaapi_account_id, trade.broker_position_id, volume=body.volume)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Partial close failed: {exc}")

    trade.reconciliation_status = "reconciliation_pending"
    db.commit()
    db.refresh(trade)
    return trade
