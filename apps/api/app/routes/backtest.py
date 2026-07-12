from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import models, schemas
from app.config import settings
from app.database import get_db
from app.services.backtest import BacktestError, run_backtest as run_engine

router = APIRouter()


@router.post("", response_model=schemas.BacktestResponse)
async def run_backtest(
    backtest_data: schemas.BacktestRequest,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Run a template-based backtest over real historical candles."""
    strategy = db.query(models.Strategy).filter(
        models.Strategy.id == backtest_data.strategy_id,
        models.Strategy.user_id == current_user["user_id"]
    ).first()

    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found"
        )

    account = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.id == backtest_data.broker_account_id,
        models.BrokerAccount.user_id == current_user["user_id"],
        models.BrokerAccount.is_active == True,
    ).first()

    if not account or not account.metaapi_account_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active broker account connected to MetaApi not found"
        )

    try:
        outcome = run_engine(
            strategy=strategy,
            metaapi_account_id=account.metaapi_account_id,
            symbol=backtest_data.symbol,
            timeframe=backtest_data.timeframe,
            start_epoch=int(backtest_data.start_date.timestamp()),
            end_epoch=int(backtest_data.end_date.timestamp()),
            initial_balance=backtest_data.initial_balance,
        )
    except BacktestError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    backtest = models.Backtest(
        user_id=current_user["user_id"],
        strategy_id=strategy.id,
        symbol=backtest_data.symbol.upper(),
        timeframe=backtest_data.timeframe.upper(),
        start_date=backtest_data.start_date.replace(tzinfo=None),
        end_date=backtest_data.end_date.replace(tzinfo=None),
        initial_balance=backtest_data.initial_balance,
        total_trades=outcome.total_trades,
        winning_trades=outcome.winning_trades,
        losing_trades=outcome.losing_trades,
        win_rate=outcome.win_rate,
        total_profit=outcome.total_profit,
        profit_factor=outcome.profit_factor,
        max_drawdown=outcome.max_drawdown,
        average_win=outcome.average_win,
        average_loss=outcome.average_loss,
        risk_reward_ratio=outcome.risk_reward_ratio,
        equity_curve=outcome.equity_curve,
        trades_log=outcome.trades_log,
        is_safe=(
            outcome.total_trades >= settings.MIN_BACKTEST_TRADES
            and outcome.profit_factor >= settings.MIN_PROFIT_FACTOR
        ),
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
