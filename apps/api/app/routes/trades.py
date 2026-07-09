from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from app import models, schemas
from app.database import get_db
from app.config import settings

router = APIRouter()


@router.post("/execute", response_model=schemas.TradeResponse)
async def execute_trade(
    trade_data: schemas.TradeExecute,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Execute a trade (demo or live based on user settings)."""
    # Get user
    user = db.query(models.User).filter(models.User.id == current_user["user_id"]).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Risk checks
    if user.trading_mode == models.TradingMode.LIVE:
        if not user.enable_live_trading:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Live trading not enabled for this user"
            )
        if not settings.ENABLE_LIVE_TRADING:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Live trading is disabled globally"
            )

    # Validate stop loss exists
    if not trade_data.stop_loss:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stop loss is required"
        )

    # Create trade record
    trade = models.Trade(
        user_id=current_user["user_id"],
        symbol=trade_data.symbol,
        trade_type=trade_data.trade_type,
        entry_price=trade_data.entry_price,
        entry_time=datetime.utcnow(),
        stop_loss=trade_data.stop_loss,
        take_profit=trade_data.take_profit,
        volume=trade_data.volume,
        notes=trade_data.notes,
        status=models.TradeStatus.OPEN,
        mode=user.trading_mode
    )

    db.add(trade)
    db.commit()
    db.refresh(trade)

    return trade


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
    exit_price: float,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Close an open trade."""
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

    # Calculate P&L
    if trade.trade_type == "buy":
        profit_loss = (exit_price - trade.entry_price) * trade.volume
    else:
        profit_loss = (trade.entry_price - exit_price) * trade.volume

    profit_loss_percent = (profit_loss / (trade.entry_price * trade.volume)) * 100 if trade.entry_price else 0

    # Update trade
    trade.exit_price = exit_price
    trade.exit_time = datetime.utcnow()
    trade.profit_loss = profit_loss
    trade.profit_loss_percent = profit_loss_percent
    trade.status = models.TradeStatus.CLOSED

    db.commit()
    db.refresh(trade)

    return trade
