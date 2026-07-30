import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services.notify import create_notification

router = APIRouter()


def _get_user_account(account_id: int, user_id: int, db: Session) -> models.BrokerAccount:
    account = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.id == account_id,
        models.BrokerAccount.user_id == user_id,
    ).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker account not found")
    return account


def _current_user_dep():
    return __import__("app.auth", fromlist=["get_current_user"]).get_current_user


@router.get("", response_model=list[schemas.BrokerAccountResponse])
async def list_broker_accounts(
    current_user: dict = Depends(_current_user_dep()),
    db: Session = Depends(get_db),
):
    """List local broker accounts without calling MetaApi."""
    return db.query(models.BrokerAccount).filter(
        models.BrokerAccount.user_id == current_user["user_id"],
    ).order_by(models.BrokerAccount.created_at.desc()).all()


@router.post("/direct-mt5", status_code=status.HTTP_201_CREATED)
async def create_direct_mt5_bridge(
    payload: dict,
    current_user: dict = Depends(_current_user_dep()),
    db: Session = Depends(get_db),
):
    """Create a direct MT5 bridge account and one-time EA API key.

    This does not call MetaApi and does not store the MT5 trading password.
    """
    name = str(payload.get("name") or "Direct MT5 bridge").strip()[:100]
    login = str(payload.get("login") or "pending").strip()[:255]
    server = str(payload.get("server") or "local-terminal").strip()[:100]
    account_type = str(payload.get("account_type") or "demo").lower()
    if account_type not in {"demo", "live"}:
        account_type = "demo"

    if login and login != "pending":
        existing = db.query(models.BrokerAccount).filter(
            models.BrokerAccount.user_id == current_user["user_id"],
            models.BrokerAccount.broker == "direct-mt5",
            models.BrokerAccount.account_id == login,
            models.BrokerAccount.server == server,
            models.BrokerAccount.is_active == True,  # noqa: E712
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An active direct bridge already exists for this MT5 login and server",
            )

    account = models.BrokerAccount(
        user_id=current_user["user_id"],
        broker="direct-mt5",
        account_id=login,
        account_type=models.TradingMode.LIVE if account_type == "live" else models.TradingMode.DEMO,
        balance=0,
        currency="USD",
        is_active=True,
        name=name,
        server=server,
        platform="mt5",
        connection_state="waiting_for_ea",
    )
    db.add(account)
    db.flush()

    raw_key = "arot_" + secrets.token_urlsafe(32)
    db.add(models.APIKey(
        user_id=current_user["user_id"],
        broker_account_id=account.id,
        key=raw_key,
        name=f"MT5 Bridge - {name}",
        is_active=True,
    ))
    create_notification(
        db,
        current_user["user_id"],
        title="Direct MT5 bridge created",
        body="Install the AroPilotEA in MetaTrader 5 and paste the generated bridge key.",
        category="system",
        link="/dashboard/broker-accounts",
    )
    db.commit()
    db.refresh(account)
    return {
        "account": schemas.BrokerAccountResponse.model_validate(account).model_dump(mode="json"),
        "api_key": raw_key,
        "endpoint": "https://arotrader.arosoftlabs.com/api/mt5/bridge",
        "ea_file": "/mt5/AroPilotEA.mq5",
    }


@router.get("/direct-mt5/{account_id}/credentials")
async def get_direct_mt5_bridge_credentials(
    account_id: int,
    current_user: dict = Depends(_current_user_dep()),
    db: Session = Depends(get_db),
):
    """Return EA inputs for an existing direct MT5 bridge."""
    account = _get_user_account(account_id, current_user["user_id"], db)
    if account.broker != "direct-mt5":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="EA inputs are only available for direct MT5 bridge accounts",
        )

    key = db.query(models.APIKey).filter(
        models.APIKey.user_id == current_user["user_id"],
        models.APIKey.broker_account_id == account.id,
        models.APIKey.is_active == True,  # noqa: E712
    ).order_by(models.APIKey.created_at.desc()).first()
    if not key:
        key = models.APIKey(
            user_id=current_user["user_id"],
            broker_account_id=account.id,
            key="arot_" + secrets.token_urlsafe(32),
            name=f"MT5 Bridge - {account.name or account.account_id}",
            is_active=True,
        )
        db.add(key)
        db.commit()
        db.refresh(key)

    return {
        "account_id": account.id,
        "api_key": key.key,
        "endpoint": "https://arotrader.arosoftlabs.com/api/mt5/bridge",
        "ea_file": "/mt5/AroPilotEA.mq5",
    }


@router.post("", response_model=schemas.BrokerAccountResponse, status_code=status.HTTP_201_CREATED)
async def add_demo_broker_account(
    account_data: schemas.BrokerAccountCreate,
    current_user: dict = Depends(_current_user_dep()),
    db: Session = Depends(get_db),
):
    """Store demo-account metadata only. Live connectivity uses direct MT5."""
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


@router.post("/mt5")
async def connect_mt5_account_disabled():
    """MetaApi broker registration is permanently disabled."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="MetaApi broker registration is disabled. Use the direct MT5 bridge.",
    )


@router.post("/{account_id}/deploy")
async def deploy_account_disabled(account_id: int):
    del account_id
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="MetaApi deploy is disabled. Use the direct MT5 bridge.",
    )


@router.post("/{account_id}/undeploy")
async def undeploy_account_disabled(account_id: int):
    del account_id
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="MetaApi undeploy is disabled. Use the direct MT5 bridge.",
    )


@router.get("/{account_id}/state")
async def refresh_account_state_disabled(account_id: int):
    del account_id
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="MetaApi state refresh is disabled. Use the direct MT5 bridge.",
    )


@router.get("/{account_id}/symbols")
async def list_account_symbols_disabled(account_id: int):
    del account_id
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="MetaApi symbol sync is disabled. Use the direct MT5 bridge.",
    )


@router.delete("/{account_id}", status_code=status.HTTP_200_OK)
async def delete_broker_account(
    account_id: int,
    current_user: dict = Depends(_current_user_dep()),
    db: Session = Depends(get_db),
):
    """Remove an account while retaining trade and analysis audit history."""
    account = _get_user_account(account_id, current_user["user_id"], db)

    nullable_references = (
        models.AIAnalysis,
        models.Signal,
        models.Trade,
        models.ScannerProfile,
        models.ExecutionIntent,
    )
    for model in nullable_references:
        values = {model.broker_account_id: None}
        if model is models.ScannerProfile:
            values[model.scan_enabled] = False
        db.query(model).filter(model.broker_account_id == account.id).update(
            values,
            synchronize_session=False,
        )
    db.query(models.BrokerSymbol).filter(
        models.BrokerSymbol.broker_account_id == account.id,
    ).delete(synchronize_session=False)
    db.query(models.APIKey).filter(
        models.APIKey.broker_account_id == account.id,
    ).delete(synchronize_session=False)
    db.delete(account)
    db.commit()

    try:
        from app.services.mt5_bridge.store import delete_account_data
        delete_account_data(account_id)
    except Exception:
        pass

    return {"status": "deleted", "account_id": account_id}


@router.post("/{account_id}/reconcile")
async def reconcile_broker_account(
    account_id: int,
    current_user: dict = Depends(_current_user_dep()),
    db: Session = Depends(get_db),
):
    """Force execution of reconciliation for a specific direct MT5 broker account."""
    from app.services.order_execution import ExecutionError, reconcile_account

    try:
        return reconcile_account(account_id, current_user["user_id"], db)
    except ExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Reconciliation failed: {exc}")
