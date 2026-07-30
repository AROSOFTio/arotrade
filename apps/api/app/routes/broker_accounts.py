import secrets
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services import metaapi_gateway as metaapi
from app.services.broker_symbol_sync import sync_broker_symbols_for_account
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


def _apply_remote_state(account: models.BrokerAccount, remote: dict) -> bool:
    """Copy MetaApi deployment state onto our local broker account row."""
    previous_state = account.connection_state
    state = metaapi.account_state(remote)
    if state:
        account.connection_state = state
    return account.connection_state != previous_state


def _remote_requires_deployment(remote: dict) -> bool:
    state = metaapi.account_state(remote)
    if state in {"deployed", "deploying"}:
        return False
    if state in {"created", "undeployed", "undeploying"}:
        return True
    return True


@router.get("", response_model=list[schemas.BrokerAccountResponse])
async def list_broker_accounts(
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db),
):
    accounts = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.user_id == current_user["user_id"]
    ).order_by(models.BrokerAccount.created_at.desc()).all()

    has_updates = False
    for account in accounts:
        if not account.is_active or not account.metaapi_account_id:
            continue
        try:
            remote = metaapi.get_account(account.metaapi_account_id)
        except metaapi.MetaApiError:
            continue
        state = metaapi.account_state(remote) or ""
        connection = (remote.get("connectionStatus") or "").lower()
        has_updates = _apply_remote_state(account, remote) or has_updates
        if state == "deployed" and connection == "connected":
            try:
                info = metaapi.get_account_information(account.metaapi_account_id)
                account.balance = float(info.get("balance") or account.balance)
                account.currency = (info.get("currency") or account.currency)[:3]
                has_updates = True
            except metaapi.MetaApiError:
                pass
            sync_result = sync_broker_symbols_for_account(db, account)
            has_updates = has_updates or sync_result.synced > 0

    if has_updates:
        db.commit()
        for account in accounts:
            db.refresh(account)

    return accounts



@router.post("/direct-mt5", status_code=status.HTTP_201_CREATED)
async def create_direct_mt5_bridge(
    payload: dict,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db),
):
    """Create a direct MT5 bridge account and one-time EA API key.

    This does not call MetaApi and does not store the MT5 trading password. The
    returned api_key is shown once and should be pasted into the MT5 EA inputs.
    """
    name = str(payload.get("name") or "Direct MT5 bridge").strip()[:100]
    login = str(payload.get("login") or "pending").strip()[:255]
    server = str(payload.get("server") or "local-terminal").strip()[:100]
    account_type = str(payload.get("account_type") or "demo").lower()
    if account_type not in {"demo", "live"}:
        account_type = "demo"

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
    api_key = models.APIKey(
        user_id=current_user["user_id"],
        key=raw_key,
        name=f"MT5 Bridge - {name}",
        is_active=True,
    )
    db.add(api_key)
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
        connection_state=metaapi.account_state(created) or "undeployed",
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
        remote = metaapi.get_account(metaapi_id)
        _apply_remote_state(account, remote)
        if _remote_requires_deployment(remote):
            metaapi.deploy_account(metaapi_id)
            remote = metaapi.get_account(metaapi_id)
            _apply_remote_state(account, remote)
    except metaapi.MetaApiError as exc:
        raise _metaapi_error(exc)
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

    state = metaapi.account_state(remote) or ""          # created/deploying/deployed/undeploying/undeployed
    connection = (remote.get("connectionStatus") or "").lower()  # connected/disconnected/connecting
    _apply_remote_state(account, remote)

    if state == "deployed" and connection == "connected":
        try:
            info = metaapi.get_account_information(metaapi_id)
            account.balance = float(info.get("balance") or account.balance)
            account.currency = (info.get("currency") or account.currency)[:3]
        except metaapi.MetaApiError:
            pass  # state still refreshes even if balance fetch fails
        sync_broker_symbols_for_account(db, account)

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
    sync_broker_symbols_for_account(db, account)
    db.commit()
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


@router.post("/{account_id}/reconcile")
async def reconcile_broker_account(
    account_id: int,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db),
):
    """Force execution of reconciliation for a specific broker account."""
    from app.services.order_execution import reconcile_account, ExecutionError
    try:
        res = reconcile_account(account_id, current_user["user_id"], db)
        return res
    except ExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Reconciliation failed: {exc}")
