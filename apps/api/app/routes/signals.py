from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.config import settings
from app.services import metaapi
from app.services.execution import PaperBroker, evaluate_signal_for_execution, utc_now
from app.services.notify import notify_signal_event
from app.services import trading_control

router = APIRouter()


@router.post("", response_model=schemas.SignalResponse)
async def create_signal(
    signal_data: schemas.SignalCreate,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new trading signal."""
    signal = models.Signal(
        user_id=current_user["user_id"],
        symbol=signal_data.symbol,
        timeframe=signal_data.timeframe,
        signal_type=signal_data.signal_type,
        entry_min=signal_data.entry_min,
        entry_max=signal_data.entry_max,
        stop_loss=signal_data.stop_loss,
        take_profit_1=signal_data.take_profit_1,
        take_profit_2=signal_data.take_profit_2,
        take_profit_3=signal_data.take_profit_3,
        risk_reward=signal_data.risk_reward,
        confidence=signal_data.confidence,
        notes=signal_data.notes,
        valid_until=signal_data.valid_until,
        status=models.SignalStatus.PENDING
    )

    db.add(signal)
    db.flush()
    user = db.query(models.User).filter(models.User.id == current_user["user_id"]).first()
    if user:
        notify_signal_event(db, user, signal, "created")
    db.commit()
    db.refresh(signal)

    return signal


def _get_user_signal(signal_id: int, user_id: int, db: Session) -> models.Signal:
    signal = db.query(models.Signal).filter(
        models.Signal.id == signal_id,
        models.Signal.user_id == user_id
    ).first()

    if not signal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signal not found")

    return signal


def _add_execution_audit(
    db: Session,
    *,
    user_id: int,
    signal_id: int,
    outcome: str,
    reason: str | None,
    details: dict,
    trade_id: int | None = None,
) -> None:
    db.add(models.ExecutionAudit(
        user_id=user_id,
        signal_id=signal_id,
        trade_id=trade_id,
        broker="paper",
        mode=models.TradingMode.DEMO.value,
        outcome=outcome,
        reason=reason,
        details=details,
    ))


@router.get("", response_model=list[schemas.SignalResponse])
async def list_signals(
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 50
):
    """List user's signals."""
    signals = db.query(models.Signal).filter(
        models.Signal.user_id == current_user["user_id"]
    ).offset(skip).limit(limit).all()

    return signals


@router.get("/{signal_id}", response_model=schemas.SignalResponse)
async def get_signal(
    signal_id: int,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Get specific signal."""
    return _get_user_signal(signal_id, current_user["user_id"], db)


@router.put("/{signal_id}/approve")
async def approve_signal(
    signal_id: int,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Approve a signal."""
    signal = _get_user_signal(signal_id, current_user["user_id"], db)

    if signal.status != models.SignalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending signals can be approved"
        )

    signal.status = models.SignalStatus.APPROVED
    signal.approved_at = utc_now()

    user = db.query(models.User).filter(models.User.id == current_user["user_id"]).first()
    if user:
        notify_signal_event(db, user, signal, "approved")

    db.commit()
    db.refresh(signal)

    return signal


@router.put("/{signal_id}/reject")
async def reject_signal(
    signal_id: int,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Reject a signal."""
    signal = _get_user_signal(signal_id, current_user["user_id"], db)

    if signal.status != models.SignalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending signals can be rejected"
        )

    signal.status = models.SignalStatus.REJECTED
    db.commit()
    db.refresh(signal)

    return signal


@router.post("/{signal_id}/evaluate", response_model=schemas.SignalEvaluationResponse)
async def evaluate_signal(
    signal_id: int,
    request: schemas.SignalEvaluationRequest,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Explain whether an approved signal is eligible for paper execution."""
    signal = _get_user_signal(signal_id, current_user["user_id"], db)
    user = db.query(models.User).filter(models.User.id == current_user["user_id"]).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    open_trade_count = db.query(models.Trade).filter(
        models.Trade.user_id == user.id,
        models.Trade.status == models.TradeStatus.OPEN,
    ).count()
    result = evaluate_signal_for_execution(signal, user, open_trade_count, request.observed_price)
    return {
        "eligible": result.eligible,
        "reasons": result.reasons,
        "calculated_risk_reward": result.calculated_risk_reward,
    }


@router.post("/{signal_id}/execute-demo", response_model=schemas.TradeResponse)
async def execute_signal_demo(
    signal_id: int,
    request: schemas.SignalPaperExecutionRequest,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Create a clearly labelled paper trade after deterministic signal checks pass."""
    control = trading_control.get_platform_control(db)
    paper_reason = trading_control.paper_block_reason(control)
    if paper_reason:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=paper_reason)

    signal = _get_user_signal(signal_id, current_user["user_id"], db)
    user = db.query(models.User).filter(models.User.id == current_user["user_id"]).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    existing_trade = db.query(models.Trade).filter(
        models.Trade.signal_id == signal.id,
        models.Trade.status == models.TradeStatus.OPEN,
    ).first()
    if existing_trade:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Signal already has an open trade")

    open_trade_count = db.query(models.Trade).filter(
        models.Trade.user_id == user.id,
        models.Trade.status == models.TradeStatus.OPEN,
    ).count()
    result = evaluate_signal_for_execution(signal, user, open_trade_count, request.observed_price)
    if not result.eligible:
        _add_execution_audit(
            db,
            user_id=user.id,
            signal_id=signal.id,
            outcome="blocked",
            reason="; ".join(result.reasons),
            details={
                "observed_price": request.observed_price,
                "calculated_risk_reward": result.calculated_risk_reward,
            },
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result.reasons)

    fill = PaperBroker().submit(request.observed_price)
    now = utc_now()
    trade = models.Trade(
        user_id=user.id,
        signal_id=signal.id,
        symbol=signal.symbol,
        trade_type=signal.signal_type,
        entry_price=fill.fill_price,
        entry_time=now,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit_1,
        volume=request.volume,
        notes=request.notes or signal.notes,
        status=models.TradeStatus.OPEN,
        mode=models.TradingMode.DEMO,
        broker=fill.broker,
        broker_order_id=fill.broker_order_id,
        client_order_id=fill.client_order_id,
        execution_status="filled",
        submitted_at=now,
        filled_at=now,
    )
    db.add(trade)
    db.flush()

    signal.status = models.SignalStatus.EXECUTED_DEMO
    signal.executed_at = now
    _add_execution_audit(
        db,
        user_id=user.id,
        signal_id=signal.id,
        trade_id=trade.id,
        outcome="filled",
        reason="Paper execution filled after signal gate passed",
        details={
            "observed_price": request.observed_price,
            "volume": request.volume,
            "calculated_risk_reward": result.calculated_risk_reward,
            "simulated": True,
        },
    )
    db.commit()
    db.refresh(trade)
    return trade


@router.post("/{signal_id}/execute-live", response_model=schemas.TradeResponse)
async def execute_signal_live(
    signal_id: int,
    request: schemas.SignalLiveExecutionRequest,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Send an approved signal to the user's connected MT5 account as a real order.

    Gates, in order: user opted into live trading and accepted the disclaimer,
    signal is approved and unexpired with a stop loss, volume within platform
    cap, no open trade for this signal, open-trade count below the user limit,
    and the broker account is a deployed MetaApi connection owned by the user.
    """
    signal = _get_user_signal(signal_id, current_user["user_id"], db)
    user = db.query(models.User).filter(models.User.id == current_user["user_id"]).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    control = trading_control.get_platform_control(db)
    platform_reason = trading_control.live_entry_block_reason(control)
    if platform_reason:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=platform_reason)

    if not user.enable_live_trading or not user.accepted_live_disclaimer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Enable live trading in Settings (and accept the risk disclaimer) first"
        )

    signal_status = getattr(signal.status, "value", signal.status)
    if signal_status != "approved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only approved signals can be executed live")
    if signal.valid_until is not None and signal.valid_until <= utc_now():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Signal has expired")
    if not signal.stop_loss or signal.stop_loss <= 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No stop loss - live execution refused")
    if request.volume > settings.MAX_LIVE_ORDER_VOLUME:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Volume exceeds the platform cap of {settings.MAX_LIVE_ORDER_VOLUME} lots"
        )

    existing_trade = db.query(models.Trade).filter(
        models.Trade.signal_id == signal.id,
        models.Trade.status == models.TradeStatus.OPEN,
    ).first()
    if existing_trade:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Signal already has an open trade")

    open_trade_count = db.query(models.Trade).filter(
        models.Trade.user_id == user.id,
        models.Trade.status == models.TradeStatus.OPEN,
    ).count()
    if open_trade_count >= user.max_open_trades:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Maximum open-trade limit reached")

    account = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.id == request.broker_account_id,
        models.BrokerAccount.user_id == user.id,
        models.BrokerAccount.is_active == True,  # noqa: E712
    ).first()
    if not account or not account.metaapi_account_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connected broker account not found")
    if account.account_type != models.TradingMode.LIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Select a verified LIVE broker account. Demo broker accounts cannot receive real-money orders."
        )
    if account.connection_state != "deployed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Broker account is not deployed - deploy it on the Broker accounts page first"
        )

    try:
        quote = metaapi.get_symbol_price(account.metaapi_account_id, signal.symbol)
    except metaapi.MetaApiError as exc:
        db.add(models.ExecutionAudit(
            user_id=user.id,
            signal_id=signal.id,
            broker=account.broker,
            mode=models.TradingMode.LIVE.value,
            outcome="rejected",
            reason=str(exc),
            details={"broker_account_id": account.id, "validation": "broker_quote"},
        ))
        db.commit()
        raise HTTPException(status_code=exc.status_code if exc.status_code >= 400 else 502, detail=f"Broker quote is missing or stale: {exc}")

    observed_price = _quote_observed_price(quote, signal.signal_type)
    if observed_price <= 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Broker quote is missing or stale")

    result = evaluate_signal_for_execution(signal, user, open_trade_count, observed_price)
    if not result.eligible:
        db.add(models.ExecutionAudit(
            user_id=user.id,
            signal_id=signal.id,
            broker=account.broker,
            mode=models.TradingMode.LIVE.value,
            outcome="blocked",
            reason="; ".join(result.reasons),
            details={
                "volume": request.volume,
                "broker_account_id": account.id,
                "observed_price": observed_price,
                "broker_quote": quote,
                "calculated_risk_reward": result.calculated_risk_reward,
            },
        ))
        db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result.reasons)

    client_order_id = f"arotrade-live-{uuid4()}"
    try:
        order_result = metaapi.place_market_order(
            metaapi_account_id=account.metaapi_account_id,
            symbol=signal.symbol,
            direction=signal.signal_type,
            volume=request.volume,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit_1,
            client_id=client_order_id,
            comment=f"AroTrade #{signal.id}",
        )
    except metaapi.MetaApiError as exc:
        db.add(models.ExecutionAudit(
            user_id=user.id,
            signal_id=signal.id,
            broker=account.broker,
            mode=models.TradingMode.LIVE.value,
            outcome="rejected",
            reason=str(exc),
            details={"volume": request.volume, "broker_account_id": account.id},
        ))
        db.commit()
        raise HTTPException(status_code=exc.status_code if exc.status_code >= 400 else 502, detail=str(exc))

    now = utc_now()
    fill_price = float(order_result.get("openPrice") or 0) or signal.entry_min
    trade = models.Trade(
        user_id=user.id,
        signal_id=signal.id,
        symbol=signal.symbol,
        trade_type=signal.signal_type,
        entry_price=fill_price,
        entry_time=now,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit_1,
        volume=request.volume,
        notes=request.notes or signal.notes,
        status=models.TradeStatus.OPEN,
        mode=models.TradingMode.LIVE,
        broker=account.broker,
        broker_order_id=str(order_result.get("orderId") or order_result.get("positionId") or ""),
        client_order_id=client_order_id,
        execution_status=(order_result.get("stringCode") or "submitted").lower(),
        submitted_at=now,
        filled_at=now if order_result.get("openPrice") else None,
    )
    db.add(trade)
    db.flush()

    signal.status = models.SignalStatus.EXECUTED_LIVE
    signal.executed_at = now
    db.add(models.ExecutionAudit(
        user_id=user.id,
        signal_id=signal.id,
        trade_id=trade.id,
        broker=account.broker,
        mode=models.TradingMode.LIVE.value,
        outcome="submitted",
        reason="Live order submitted via MetaApi",
        details={
            "volume": request.volume,
            "broker_account_id": account.id,
            "metaapi_response": order_result,
        },
    ))


def _quote_observed_price(quote: dict, direction: str) -> float:
    bid = quote.get("bid") or quote.get("brokerBid")
    ask = quote.get("ask") or quote.get("brokerAsk")
    price = ask if direction == "buy" else bid
    price = price or quote.get("price") or quote.get("last") or quote.get("close")
    try:
        return float(price)
    except (TypeError, ValueError):
        return 0.0
    notify_signal_event(db, user, signal, "executed_live")
    db.commit()
    db.refresh(trade)
    return trade
