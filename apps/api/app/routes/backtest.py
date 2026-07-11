from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db

router = APIRouter()


@router.post("", response_model=schemas.BacktestResponse)
async def run_backtest(
    backtest_data: schemas.BacktestRequest,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Run a backtest for a strategy."""
    # Verify strategy exists
    strategy = db.query(models.Strategy).filter(
        models.Strategy.id == backtest_data.strategy_id,
        models.Strategy.user_id == current_user["user_id"]
    ).first()

    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found"
        )

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Backtesting needs verified historical candle data and executable strategy rules. No results are generated until those are connected."
    )


@router.get("/{backtest_id}", response_model=schemas.BacktestResponse)
async def get_backtest(
    backtest_id: int,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Get backtest results."""
    backtest = db.query(models.Backtest).filter(
        models.Backtest.id == backtest_id,
        models.Backtest.user_id == current_user["user_id"]
    ).first()

    if not backtest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest not found"
        )

    return backtest
