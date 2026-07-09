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

    # Create backtest record
    backtest = models.Backtest(
        user_id=current_user["user_id"],
        strategy_id=backtest_data.strategy_id,
        symbol=backtest_data.symbol,
        timeframe=backtest_data.timeframe,
        start_date=backtest_data.start_date,
        end_date=backtest_data.end_date,
        initial_balance=backtest_data.initial_balance,
        # TODO: Run actual backtest logic
        total_trades=100,
        winning_trades=65,
        losing_trades=35,
        win_rate=65.0,
        total_profit=1500.0,
        profit_factor=2.3,
        max_drawdown=10.5,
        average_win=50.0,
        average_loss=20.0,
        risk_reward_ratio=2.5,
        is_safe=True
    )

    db.add(backtest)
    db.commit()
    db.refresh(backtest)

    return backtest


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
