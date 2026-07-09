from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db

router = APIRouter()


@router.post("", response_model=schemas.StrategyResponse)
async def create_strategy(
    strategy_data: schemas.StrategyCreate,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new trading strategy."""
    strategy = models.Strategy(
        user_id=current_user["user_id"],
        name=strategy_data.name,
        description=strategy_data.description,
        trend_indicators=strategy_data.trend_indicators,
        momentum_indicators=strategy_data.momentum_indicators,
        volume_indicators=strategy_data.volume_indicators,
        smart_money=strategy_data.smart_money,
        risk_per_trade=strategy_data.risk_per_trade,
        max_daily_loss=strategy_data.max_daily_loss,
        max_open_trades=strategy_data.max_open_trades,
        allow_martingale=strategy_data.allow_martingale,
        health_score=0
    )

    db.add(strategy)
    db.commit()
    db.refresh(strategy)

    return strategy


@router.get("", response_model=list[schemas.StrategyResponse])
async def list_strategies(
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 50
):
    """List user's strategies."""
    strategies = db.query(models.Strategy).filter(
        models.Strategy.user_id == current_user["user_id"]
    ).offset(skip).limit(limit).all()

    return strategies


@router.get("/{strategy_id}", response_model=schemas.StrategyResponse)
async def get_strategy(
    strategy_id: int,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Get specific strategy."""
    strategy = db.query(models.Strategy).filter(
        models.Strategy.id == strategy_id,
        models.Strategy.user_id == current_user["user_id"]
    ).first()

    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found"
        )

    return strategy


@router.delete("/{strategy_id}")
async def delete_strategy(
    strategy_id: int,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a strategy."""
    strategy = db.query(models.Strategy).filter(
        models.Strategy.id == strategy_id,
        models.Strategy.user_id == current_user["user_id"]
    ).first()

    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found"
        )

    db.delete(strategy)
    db.commit()

    return {"message": "Strategy deleted"}
