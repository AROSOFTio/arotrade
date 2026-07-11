from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.config import settings
from app.services.execution import PaperBroker, evaluate_signal_for_execution, utc_now

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
    if not settings.PAPER_TRADING_ENABLED:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Paper trading is disabled")

    signal = _get_user_signal(signal_id, current_user["user_id"], db)
    user = db.query(models.User).filter(models.User.id == current_user["user_id"]).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.trading_mode != models.TradingMode.DEMO:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Switch to demo mode before executing a paper trade"
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
