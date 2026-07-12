from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.config import settings
from app.services import metaapi_gateway as metaapi
from app.services.execution import evaluate_signal_for_execution, utc_now
from app.services.notify import notify_signal_event
from app.services import trading_control
from app.services.position_sizing import calculate_position_size, spec_from_metaapi_specification
from app.services.risk_engine import run_risk_checks

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
    request: schemas.SignalApproveRequest,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Approve a signal and configure its tracking/execution parameters."""
    signal = _get_user_signal(signal_id, current_user["user_id"], db)

    if signal.status != models.SignalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending signals can be approved"
        )

    # Verify broker account
    account = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.id == request.broker_account_id,
        models.BrokerAccount.user_id == current_user["user_id"],
        models.BrokerAccount.is_active == True,
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Broker account not found")

    signal.status = models.SignalStatus.APPROVED
    signal.approved_at = utc_now()
    signal.approved_action = "wait_for_entry"
    signal.broker_account_id = request.broker_account_id
    signal.execution_mode = request.execution_mode
    signal.broker_symbol = signal.broker_symbol or signal.symbol

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
    signal.approved_action = "reject"
    db.commit()
    db.refresh(signal)
    return signal


@router.post("/{signal_id}/preview")
async def preview_execution(
    signal_id: int,
    request: schemas.SignalExecuteRequest,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Calculate sizing and check risk gates for a preview of execution."""
    user = db.query(models.User).filter(models.User.id == current_user["user_id"]).first()
    signal = _get_user_signal(signal_id, current_user["user_id"], db)
    account = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.id == request.broker_account_id,
        models.BrokerAccount.user_id == current_user["user_id"],
        models.BrokerAccount.is_active == True,
    ).first()
    if not user or not account:
        raise HTTPException(status_code=404, detail="User or account not found")

    try:
        quote = metaapi.get_symbol_price(account.metaapi_account_id, signal.broker_symbol or signal.symbol, require_fresh=True)
        spec_dict = metaapi.get_symbol_specification(account.metaapi_account_id, signal.broker_symbol or signal.symbol)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch quote/specs: {exc}")

    spec = spec_from_metaapi_specification(spec_dict)
    if not spec:
        raise HTTPException(status_code=400, detail="Incomplete symbol specifications")

    observed_price = metaapi.extract_observed_price(quote, signal.signal_type)

    # Sizing
    risk_percent = signal.scanner_profile.risk_percent if signal.scanner_profile else user.default_risk_percent
    sizing = calculate_position_size(
        equity=account.balance or 10000,
        risk_percent=risk_percent,
        entry_price=observed_price,
        stop_loss=signal.stop_loss,
        spec=spec,
        free_margin=account.balance or 10000,
        direction=signal.signal_type,
        platform_max_volume=settings.MAX_LIVE_ORDER_VOLUME
    )

    # Risk Engine
    open_trade_count = db.query(models.Trade).filter(
        models.Trade.user_id == user.id,
        models.Trade.status == models.TradeStatus.OPEN,
    ).count()
    from app.services.execution import _get_daily_loss
    daily_loss = _get_daily_loss(db, user.id)

    quote_time_str = quote.get("time") or quote.get("brokerTime")
    risk_result = run_risk_checks(
        db=db,
        signal=signal,
        user=user,
        account=account,
        observed_price=observed_price,
        volume=sizing.final_volume,
        execution_mode=request.execution_mode,
        quote=quote,
        quote_time_str=quote_time_str,
        open_trade_count=open_trade_count,
        daily_realized_pnl=daily_loss,
        equity=account.balance or 10000,
        free_margin=account.balance or 10000,
        is_jump_in=True,
    )

    return {
        "eligible": risk_result.approved and not sizing.blocked,
        "reasons": risk_result.reasons + ([sizing.block_reason] if sizing.blocked else []),
        "calculated_volume": sizing.final_volume,
        "observed_price": observed_price,
        "bid": quote.get("bid") or quote.get("brokerBid"),
        "ask": quote.get("ask") or quote.get("brokerAsk"),
        "spread": quote.get("spread") or 0.0,
        "risk_amount": sizing.risk_amount,
        "loss_per_lot": sizing.loss_per_lot,
    }


@router.post("/{signal_id}/execute", response_model=schemas.TradeResponse)
async def execute_signal(
    signal_id: int,
    request: schemas.SignalExecuteRequest,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Execute a trade for an approved signal."""
    from app.services.execution import execute_signal_trade, ExecutionError
    try:
        trade = execute_signal_trade(
            db,
            user_id=current_user["user_id"],
            signal_id=signal_id,
            broker_account_id=request.broker_account_id,
            execution_mode=request.execution_mode,
            is_jump_in=True,
            preview_price=request.preview_price,
        )
        return trade
    except ExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# Legacy wrappers for backward compatibility with external/test callers
@router.post("/{signal_id}/execute-demo", response_model=schemas.TradeResponse)
async def execute_signal_demo(
    signal_id: int,
    request: schemas.SignalPaperExecutionRequest,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Paper execution fallback wrapper."""
    account = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.user_id == current_user["user_id"],
        models.BrokerAccount.is_active == True,
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="No active broker account found")

    from app.services.execution import execute_signal_trade, ExecutionError
    # map demo client request to paper execution if no demo MT5 connected, or broker_demo if it is
    mode = "broker_demo" if account.account_type == models.TradingMode.DEMO else "paper"
    try:
        return execute_signal_trade(
            db,
            user_id=current_user["user_id"],
            signal_id=signal_id,
            broker_account_id=account.id,
            execution_mode=mode,
            is_jump_in=True,
            preview_price=request.observed_price,
        )
    except ExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/{signal_id}/execute-live", response_model=schemas.TradeResponse)
async def execute_signal_live(
    signal_id: int,
    request: schemas.SignalLiveExecutionRequest,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Live execution fallback wrapper."""
    from app.services.execution import execute_signal_trade, ExecutionError
    try:
        return execute_signal_trade(
            db,
            user_id=current_user["user_id"],
            signal_id=signal_id,
            broker_account_id=request.broker_account_id,
            execution_mode="live",
            is_jump_in=True,
        )
    except ExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
