from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db

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
        status=models.SignalStatus.PENDING
    )

    db.add(signal)
    db.commit()
    db.refresh(signal)

    return signal


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
    signal = db.query(models.Signal).filter(
        models.Signal.id == signal_id,
        models.Signal.user_id == current_user["user_id"]
    ).first()

    if not signal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signal not found"
        )

    return signal


@router.put("/{signal_id}/approve")
async def approve_signal(
    signal_id: int,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Approve a signal."""
    signal = db.query(models.Signal).filter(
        models.Signal.id == signal_id,
        models.Signal.user_id == current_user["user_id"]
    ).first()

    if not signal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signal not found"
        )

    signal.status = models.SignalStatus.APPROVED
    from datetime import datetime
    signal.approved_at = datetime.utcnow()

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
    signal = db.query(models.Signal).filter(
        models.Signal.id == signal_id,
        models.Signal.user_id == current_user["user_id"]
    ).first()

    if not signal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signal not found"
        )

    signal.status = models.SignalStatus.REJECTED
    db.commit()
    db.refresh(signal)

    return signal
