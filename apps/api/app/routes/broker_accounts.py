from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter()


@router.get("", response_model=list[schemas.BrokerAccountResponse])
async def list_broker_accounts(
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(models.BrokerAccount).filter(
        models.BrokerAccount.user_id == current_user["user_id"]
    ).order_by(models.BrokerAccount.created_at.desc()).all()


@router.post("", response_model=schemas.BrokerAccountResponse, status_code=status.HTTP_201_CREATED)
async def add_demo_broker_account(
    account_data: schemas.BrokerAccountCreate,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db),
):
    """Store demo-account metadata. Credentials and real execution are not accepted here."""
    broker = account_data.broker.strip().lower()
    account_id = account_data.account_id.strip()
    existing = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.user_id == current_user["user_id"],
        models.BrokerAccount.broker == broker,
        models.BrokerAccount.account_id == account_id,
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This demo account is already listed")

    account = models.BrokerAccount(
        user_id=current_user["user_id"],
        broker=broker,
        account_id=account_id,
        account_type=models.TradingMode.DEMO,
        balance=account_data.balance,
        currency=account_data.currency.upper(),
        is_active=True,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.post("/{account_id}/deactivate", response_model=schemas.BrokerAccountResponse)
async def deactivate_broker_account(
    account_id: int,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db),
):
    account = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.id == account_id,
        models.BrokerAccount.user_id == current_user["user_id"],
    ).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker account not found")

    account.is_active = False
    db.commit()
    db.refresh(account)
    return account
