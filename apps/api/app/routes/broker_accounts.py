from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services import metaapi
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


def _require_metaapi(account: models.BrokerAccount) -> str:
    if not account.metaapi_account_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This account is not connected through MetaApi"
        )
    return account.metaapi_account_id


def _metaapi_error(exc: metaapi.MetaApiError) -> HTTPException:
    return HTTPException(status_code=exc.status_code if exc.status_code >= 400 else 502, detail=str(exc))


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


@router.post("/mt5", response_model=schemas.BrokerAccountResponse, status_code=status.HTTP_201_CREATED)
async def connect_mt5_account(
    payload: schemas.MT5ConnectRequest,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db),
):
    """Register an MT4/MT5 account (e.g. Exness) with MetaApi.

    The account is created UNDEPLOYED so no hourly charge starts until the
    user explicitly deploys it. The broker password is forwarded to MetaApi
    and never stored in our database.
    """
    existing = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.user_id == current_user["user_id"],
        models.BrokerAccount.account_id == payload.login.strip(),
        models.BrokerAccount.server == payload.server.strip(),
        models.BrokerAccount.is_active == True,  # noqa: E712
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This MT5 account is already connected")

    try:
        created = metaapi.create_account(
            name=payload.name.strip(),
            login=payload.login.strip(),
            password=payload.password,
            server=payload.server.strip(),
            platform=payload.platform,
        )
    except metaapi.MetaApiError as exc:
        raise _metaapi_error(exc)

    metaapi_account_id = metaapi.account_identifier(created)
    if not metaapi_account_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="MetaApi created the account but did not return an account id"
        )

    account = models.BrokerAccount(
        user_id=current_user["user_id"],
        broker="exness-mt5" if "exness" in payload.server.lower() else f"{payload.platform}-broker",
        account_id=payload.login.strip(),
        account_type=models.TradingMode.LIVE if payload.account_type == "live" else models.TradingMode.DEMO,
        currency="USD",
        is_active=True,
        name=payload.name.strip(),
        server=payload.server.strip(),
        platform=payload.platform,
        metaapi_account_id=metaapi_account_id,
        connection_state="undeployed",
    )
    db.add(account)
    create_notification(
        db, current_user["user_id"],
        title=f"Broker account connected: {payload.name}",
        body=f"{payload.server} · login {payload.login}. Deploy it to start the connection (hourly billing applies while deployed).",
        category="system",
        link="/dashboard/broker-accounts",
    )
    db.commit()
    db.refresh(account)
    return account


@router.post("/{account_id}/deploy", response_model=schemas.BrokerAccountResponse)
async def deploy_account(
    account_id: int,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db),
):
    """Deploy the MetaApi connection (starts hourly billing on MetaApi)."""
    account = _get_user_account(account_id, current_user["user_id"], db)
    metaapi_id = _require_metaapi(account)
    try:
        metaapi.deploy_account(metaapi_id)
    except metaapi.MetaApiError as exc:
        raise _metaapi_error(exc)
    account.connection_state = "deploying"
    db.commit()
    db.refresh(account)
    return account


@router.post("/{account_id}/undeploy", response_model=schemas.BrokerAccountResponse)
async def undeploy_account(
    account_id: int,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db),
):
    """Undeploy the MetaApi connection (stops hourly billing)."""
    account = _get_user_account(account_id, current_user["user_id"], db)
    metaapi_id = _require_metaapi(account)
    try:
        metaapi.undeploy_account(metaapi_id)
    except metaapi.MetaApiError as exc:
        raise _metaapi_error(exc)
    account.connection_state = "undeploying"
    db.commit()
    db.refresh(account)
    return account


@router.get("/{account_id}/state", response_model=schemas.BrokerAccountResponse)
async def refresh_account_state(
    account_id: int,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db),
):
    """Pull current deployment/connection state (and balance when connected) from MetaApi."""
    account = _get_user_account(account_id, current_user["user_id"], db)
    metaapi_id = _require_metaapi(account)
    try:
        remote = metaapi.get_account(metaapi_id)
    except metaapi.MetaApiError as exc:
        raise _metaapi_error(exc)

    state = (remote.get("state") or "").lower()          # CREATED/DEPLOYING/DEPLOYED/UNDEPLOYING/UNDEPLOYED
    connection = (remote.get("connectionStatus") or "").lower()  # connected/disconnected/connecting
    account.connection_state = "deployed" if state == "deployed" else (state or account.connection_state)

    if state == "deployed" and connection == "connected":
        try:
            info = metaapi.get_account_information(metaapi_id)
            account.balance = float(info.get("balance") or account.balance)
            account.currency = (info.get("currency") or account.currency)[:3]
        except metaapi.MetaApiError:
            pass  # state still refreshes even if balance fetch fails

    db.commit()
    db.refresh(account)
    return account


@router.get("/{account_id}/symbols")
async def list_account_symbols(
    account_id: int,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db),
):
    """Real tradable symbol list from the connected broker (account must be deployed)."""
    account = _get_user_account(account_id, current_user["user_id"], db)
    metaapi_id = _require_metaapi(account)
    try:
        symbols = metaapi.get_symbols(metaapi_id)
    except metaapi.MetaApiError as exc:
        raise _metaapi_error(exc)
    return {"symbols": symbols}


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
