"""Manual order API routes.

POST /api/orders/preview  — compute sizing, margin, risk warnings
POST /api/orders/execute  — submit a manual market order to the broker
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import schemas
from app.database import get_db
from app.services.order_execution import (
    ExecutionError,
    execute_manual_order,
    preview_manual_order,
)

router = APIRouter()


@router.post("/preview", response_model=schemas.ManualOrderPreviewResponse)
async def preview_order(
    body: schemas.ManualOrderPreviewRequest,
    current_user: dict = Depends(
        __import__('app.auth', fromlist=['get_current_user']).get_current_user
    ),
    db: Session = Depends(get_db),
):
    """Preview a manual market order without submitting it."""
    try:
        result = preview_manual_order(
            db,
            user_id=current_user["user_id"],
            broker_account_id=body.broker_account_id,
            symbol=body.symbol,
            direction=body.direction,
            stop_loss=body.stop_loss,
            take_profit=body.take_profit,
            volume=body.volume,
            risk_percent=body.risk_percent,
        )
        return result
    except ExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Preview failed: {exc}",
        )


@router.post("/execute", response_model=schemas.TradeResponse)
async def execute_order(
    body: schemas.ManualOrderExecuteRequest,
    current_user: dict = Depends(
        __import__('app.auth', fromlist=['get_current_user']).get_current_user
    ),
    db: Session = Depends(get_db),
):
    """Execute a manual market order via MetaApi."""
    try:
        trade = execute_manual_order(
            db,
            user_id=current_user["user_id"],
            broker_account_id=body.broker_account_id,
            symbol=body.symbol,
            direction=body.direction,
            stop_loss=body.stop_loss,
            take_profit=body.take_profit,
            volume=body.volume,
            risk_percent=body.risk_percent,
            idempotency_key=body.idempotency_key,
        )
        return trade
    except ExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Execution failed: {exc}",
        )
