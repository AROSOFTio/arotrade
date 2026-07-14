from __future__ import annotations

import logging
import redis
from datetime import datetime, UTC
from secrets import token_hex
from typing import Optional
from uuid import uuid4
from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app import models
from app.config import settings
from app.services import metaapi_gateway as metaapi
from app.services.position_sizing import calculate_position_size, spec_from_metaapi_specification
from app.services.risk_engine import run_risk_checks

logger = logging.getLogger(__name__)
redis_client = redis.Redis.from_url(settings.REDIS_URL)

class ExecutionError(Exception):
    """Raised when execution fails or is blocked."""
    pass

from dataclasses import dataclass

@dataclass
class SignalGateResult:
    eligible: bool
    reasons: list[str]
    calculated_risk_reward: Optional[float]


@dataclass
class BrokerAccountMetrics:
    balance: float
    equity: float
    free_margin: float
    margin: float
    raw: dict
    is_simulated: bool = False


@dataclass
class LiveAccountVerification:
    broker: str
    server: str
    masked_login: str
    currency: str
    is_real: bool
    trade_allowed: bool
    connected: bool
    synchronized: bool
    raw_account: dict
    raw_information: dict

def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _mask_login(value: object) -> str:
    login = str(value or "")
    if len(login) <= 4:
        return "****" if login else "unknown"
    return f"{login[:2]}****{login[-2:]}"


def _info_bool(info: dict, *keys: str) -> bool | None:
    for key in keys:
        if key not in info:
            continue
        value = info.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("true", "yes", "enabled", "allowed"):
                return True
            if lowered in ("false", "no", "disabled", "readonly", "read_only"):
                return False
    return None


def _looks_real_account(*values: object) -> bool:
    joined = " ".join(str(value or "") for value in values).lower()
    if any(marker in joined for marker in ("demo", "contest", "practice", "trial")):
        return False
    return "real" in joined or "live" in joined


def _info_text(info: dict, *keys: str) -> str:
    for key in keys:
        value = info.get(key)
        if value is not None:
            return str(value)
    return ""


def verify_live_broker_account(account: models.BrokerAccount) -> LiveAccountVerification:
    """Verify a live account from fresh MetaApi data, not local DB account_type."""
    if not account.metaapi_account_id:
        raise ExecutionError("Broker account is not connected to MetaApi.")
    try:
        remote = metaapi.get_account(account.metaapi_account_id)
        info = metaapi.get_account_information(account.metaapi_account_id)
    except Exception as exc:
        raise ExecutionError(f"MetaApi live-account verification failed: {exc}") from exc

    state = str(remote.get("state") or "").upper()
    connection = str(remote.get("connectionStatus") or "").upper()
    sync_state = str(
        remote.get("synchronizationStatus")
        or remote.get("synchronization_state")
        or info.get("synchronizationStatus")
        or ""
    ).lower()
    account_trade_mode = _info_text(
        info,
        "type",
        "accountType",
        "account_type",
        "tradeMode",
        "trade_mode",
        "accountTradeMode",
    )
    trade_allowed = _info_bool(info, "tradeAllowed", "trade_allowed", "tradingAllowed")
    connected = state == "DEPLOYED" and connection == "CONNECTED"
    synchronized = True if not sync_state else sync_state in ("synchronized", "synchronised", "connected")

    verification = LiveAccountVerification(
        broker=str(remote.get("broker") or account.broker or "unknown"),
        server=str(remote.get("server") or account.server or "unknown"),
        masked_login=_mask_login(remote.get("login") or info.get("login") or account.account_id),
        currency=str(info.get("currency") or account.currency or "USD"),
        is_real=account_trade_mode.upper() == "ACCOUNT_TRADE_MODE_REAL",
        trade_allowed=bool(trade_allowed),
        connected=connected,
        synchronized=synchronized,
        raw_account=remote,
        raw_information=info,
    )

    failures: list[str] = []
    if not verification.is_real:
        failures.append("broker account information type is not ACCOUNT_TRADE_MODE_REAL")
    if trade_allowed is not True:
        failures.append("broker tradeAllowed is not true")
    if state != "DEPLOYED":
        failures.append("MetaApi provisioning account state is not DEPLOYED")
    if connection != "CONNECTED":
        failures.append("MetaApi connectionStatus is not CONNECTED")
    if failures:
        raise ExecutionError("Live account verification failed: " + "; ".join(failures))
    return verification

def _required_account_float(info: dict, *keys: str) -> float:
    for key in keys:
        value = info.get(key)
        if value is None:
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        return parsed
    raise ExecutionError(f"MetaApi account information is missing {keys[0]}.")


def get_broker_account_metrics(account: models.BrokerAccount, execution_mode: str) -> BrokerAccountMetrics:
    """
    Return account metrics for sizing.

    Broker-demo and live modes must use actual MT5 values. Paper mode may fall
    back to the configured simulation balance if account information is not
    available, because no broker order is submitted.
    """
    try:
        info = metaapi.get_account_information(account.metaapi_account_id)
    except Exception as exc:
        if execution_mode == "paper":
            balance = float(settings.DEMO_INITIAL_BALANCE)
            return BrokerAccountMetrics(
                balance=balance,
                equity=balance,
                free_margin=balance,
                margin=0.0,
                raw={"simulation_balance": balance, "reason": str(exc)},
                is_simulated=True,
            )
        raise ExecutionError(f"MetaApi could not return actual account information: {exc}") from exc

    return BrokerAccountMetrics(
        balance=_required_account_float(info, "balance"),
        equity=_required_account_float(info, "equity"),
        free_margin=_required_account_float(info, "freeMargin", "free_margin"),
        margin=_required_account_float(info, "margin"),
        raw=info,
    )


def _lookup_tradeable_broker_symbol(db: Session, account_id: int, lookup: str) -> Optional[str]:
    broker_symbol = db.query(models.BrokerSymbol).filter(
        models.BrokerSymbol.broker_account_id == account_id,
        func.upper(func.trim(models.BrokerSymbol.broker_symbol)) == lookup,
        models.BrokerSymbol.trade_allowed == True,  # noqa: E712
    ).first()
    if broker_symbol:
        return broker_symbol.broker_symbol

    broker_symbol = db.query(models.BrokerSymbol).filter(
        models.BrokerSymbol.broker_account_id == account_id,
        func.upper(func.trim(models.BrokerSymbol.canonical_symbol)) == lookup,
        models.BrokerSymbol.trade_allowed == True,  # noqa: E712
    ).first()
    if broker_symbol:
        return broker_symbol.broker_symbol

    return None


def resolve_broker_symbol(db: Session, canonical_symbol: str, account: models.BrokerAccount) -> str:
    """Resolve the exact broker symbol for a specific account.

    The UI may submit either a canonical symbol (XAUUSD) or an exact broker
    symbol (XAUUSDm, US30_x10m). Prefer exact broker-symbol matches first,
    then fall back to canonical mapping.
    """
    requested = str(canonical_symbol or "").strip()
    lookup = requested.upper()
    if not lookup:
        raise ExecutionError("No symbol provided to resolve.")

    broker_symbol = _lookup_tradeable_broker_symbol(db, account.id, lookup)
    if broker_symbol:
        return broker_symbol

    try:
        from app.services.broker_symbol_sync import sync_broker_symbols_for_account

        sync_result = sync_broker_symbols_for_account(db, account)
        if sync_result.synced:
            db.flush()
            broker_symbol = _lookup_tradeable_broker_symbol(db, account.id, lookup)
    except Exception as exc:
        logger.info("Could not refresh broker symbols for account %s: %s", account.id, exc)

    if broker_symbol:
        return broker_symbol

    # Fallback: check the broker directly for the requested exact name.
    try:
        metaapi.get_symbol_specification(account.metaapi_account_id, requested)
    except Exception as exc:
        raise ExecutionError(
            f"Exact broker symbol for {requested} is not configured for this account. "
            "Refresh broker symbols before executing."
        ) from exc

    return requested

def resolve_signal_broker_symbol(db: Session, signal: models.Signal, account: models.BrokerAccount) -> str:
    """Resolve and persist the exact broker symbol for this signal's account."""
    canonical = (getattr(signal, "canonical_symbol", None) or signal.symbol or "").upper().strip()
    resolved = resolve_broker_symbol(db, canonical, account)
    signal.broker_symbol = resolved
    signal.canonical_symbol = canonical
    return resolved


def make_broker_client_id(signal_id: int) -> str:
    return f"AT{signal_id:X}{token_hex(3).upper()}"


def _find_confirmed_position(
    account: models.BrokerAccount,
    *,
    client_order_id: str,
    comment: str,
) -> tuple[str, str, str] | None:
    """Locate the real broker position by strict identity (clientId/comment) only.

    Shape-only matching (symbol/direction/volume) is deliberately removed to
    prevent matching the wrong position when multiple orders for the same
    instrument are open concurrently.
    """
    candidates = []
    try:
        candidates.extend(metaapi.get_positions(account.metaapi_account_id))
    except Exception:
        return None

    for pos in candidates:
        pos_text = " ".join(str(pos.get(key, "")) for key in ("clientId", "comment", "id", "positionId", "orderId"))
        if client_order_id and client_order_id in pos_text:
            pass  # identity match
        elif comment and comment in pos_text:
            pass  # identity match
        else:
            continue
        position_id = str(pos.get("id") or pos.get("positionId") or "")
        if position_id:
            return (
                str(pos.get("orderId") or ""),
                position_id,
                str(pos.get("dealId") or ""),
            )

    return None

def evaluate_signal_for_execution(signal, user, open_trade_count: int, observed_price: float, now: Optional[datetime] = None) -> SignalGateResult:
    """Apply deterministic safeguards before a signal can create a paper order."""
    now = now or utc_now()
    reasons: list[str] = []

    if not user.is_active:
        reasons.append("User account is inactive")
    signal_status = getattr(signal.status, "value", signal.status)
    if signal_status != "approved":
        reasons.append("Signal must be approved before execution")
    if signal.valid_until is not None and signal.valid_until <= now:
        reasons.append("Signal has expired")
    if signal.confidence < settings.MIN_SIGNAL_CONFIDENCE:
        reasons.append(f"Signal confidence is below {settings.MIN_SIGNAL_CONFIDENCE}%")
    if open_trade_count >= user.max_open_trades:
        reasons.append("Maximum open-trade limit reached")
    if not (signal.entry_min <= observed_price <= signal.entry_max):
        reasons.append("Observed price is outside the signal entry range")

    risk_reward = None
    if signal.signal_type == "buy":
        if signal.stop_loss >= observed_price:
            reasons.append("Buy stop loss must be below the observed price")
        if signal.take_profit_1 is None or signal.take_profit_1 <= observed_price:
            reasons.append("Buy signal requires a take-profit above the observed price")
        elif observed_price > signal.stop_loss:
            risk_reward = (signal.take_profit_1 - observed_price) / (observed_price - signal.stop_loss)
    elif signal.signal_type == "sell":
        if signal.stop_loss <= observed_price:
            reasons.append("Sell stop loss must be above the observed price")
        if signal.take_profit_1 is None or signal.take_profit_1 >= observed_price:
            reasons.append("Sell signal requires a take-profit below the observed price")
        elif signal.stop_loss > observed_price:
            risk_reward = (observed_price - signal.take_profit_1) / (signal.stop_loss - observed_price)
    else:
        reasons.append("Signal direction must be buy or sell")

    if risk_reward is not None and risk_reward < settings.MIN_SIGNAL_RISK_REWARD:
        reasons.append(
            f"Calculated reward-to-risk is below {settings.MIN_SIGNAL_RISK_REWARD:.2f}"
        )

    return SignalGateResult(
        eligible=not reasons,
        reasons=reasons,
        calculated_risk_reward=risk_reward,
    )

def _get_daily_loss(db: Session, user_id: int) -> float:
    """Calculate the user's realized profit/loss for today."""
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
    closed_today = db.query(models.Trade).filter(
        models.Trade.user_id == user_id,
        models.Trade.status == models.TradeStatus.CLOSED,
        models.Trade.exit_time >= today_start
    ).all()
    return sum(float(t.profit_loss or 0) for t in closed_today)

def execute_signal_trade(
    db: Session,
    *,
    user_id: int,
    signal_id: int,
    broker_account_id: int,
    execution_mode: str,  # paper / broker_demo / live
    is_jump_in: bool = False,
    preview_price: Optional[float] = None,
) -> models.Trade:
    """
    Authoritative order execution entry point. Implements Redis distributed locks,
    database row locking, backend sizing, safety risk checks, and idempotency logic.
    """
    if execution_mode not in ("paper", "broker_demo", "live"):
        raise ExecutionError(f"Invalid execution mode: {execution_mode}")

    # Acquire Redis distributed lock for the signal to prevent duplicate orders
    lock_key = f"lock:signal:execute:{signal_id}:{execution_mode}"
    lock = redis_client.lock(lock_key, timeout=30)
    if not lock.acquire(blocking=True, blocking_timeout=10):
        raise ExecutionError("Could not acquire concurrent execution lock for this signal.")

    try:
        # Load user and broker account
        user = db.query(models.User).filter(models.User.id == user_id).first()
        account = db.query(models.BrokerAccount).filter(
            models.BrokerAccount.id == broker_account_id,
            models.BrokerAccount.user_id == user_id,
            models.BrokerAccount.is_active == True,
        ).first()

        if not user or not account:
            raise ExecutionError("User or Broker account not found.")

        # Database row lock on the signal — filter by user_id to prevent cross-user access
        signal = db.query(models.Signal).filter(
            models.Signal.id == signal_id,
            models.Signal.user_id == user_id,
        ).with_for_update().first()
        if not signal:
            raise ExecutionError("Signal not found or does not belong to this user.")

        # Safety Check: Duplicate trades or intents
        existing_trade = db.query(models.Trade).filter(
            models.Trade.signal_id == signal_id,
            models.Trade.status == models.TradeStatus.OPEN,
        ).first()
        if existing_trade:
            return existing_trade

        existing_intent = db.query(models.ExecutionIntent).filter(
            models.ExecutionIntent.signal_id == signal_id,
            models.ExecutionIntent.execution_mode == execution_mode,
            models.ExecutionIntent.status.in_(["CREATED", "VALIDATING", "SUBMITTING", "BROKER_ACCEPTED", "FILLED", "UNCERTAIN"]),
        ).first()
        if existing_intent:
            existing_trade_for_intent = db.query(models.Trade).filter(
                models.Trade.execution_intent_id == existing_intent.id,
            ).first()
            if existing_trade_for_intent:
                return existing_trade_for_intent
            raise ExecutionError(f"Execution intent is already {existing_intent.status} for this signal.")

        live_verification = verify_live_broker_account(account) if execution_mode == "live" else None
        broker_symbol = resolve_signal_broker_symbol(db, signal, account)

        # Get MT5 Quote and Specifications
        try:
            quote = metaapi.get_symbol_price(account.metaapi_account_id, broker_symbol, require_fresh=True)
            spec_dict = metaapi.get_symbol_specification(account.metaapi_account_id, broker_symbol)
        except Exception as exc:
            raise ExecutionError(f"Failed to fetch broker data for {broker_symbol}: {exc}")

        spec = spec_from_metaapi_specification(spec_dict, quote)
        if not spec:
            raise ExecutionError(f"Incomplete broker specifications for {broker_symbol}.")

        metrics = get_broker_account_metrics(account, execution_mode)
        equity = metrics.equity
        free_margin = metrics.free_margin

        observed_price = metaapi.extract_observed_price(quote, signal.signal_type)
        if observed_price <= 0:
            raise ExecutionError("Observed price is invalid.")

        # Slippage check for Jump In Now
        if is_jump_in and preview_price is not None:
            pct_change = abs(observed_price - preview_price) / preview_price
            if pct_change > 0.003: # 0.3% max slippage tolerance
                raise ExecutionError(f"Price moved too fast (slipped {pct_change*100:.2f}%). Execution rejected.")

        # Backend Sizing (equity, risk_percent, prices, specs)
        risk_percent = signal.scanner_profile.risk_percent if signal.scanner_profile else user.default_risk_percent
        sizing = calculate_position_size(
            equity=equity,
            risk_percent=risk_percent,
            entry_price=observed_price,
            stop_loss=signal.stop_loss,
            spec=spec,
            direction=signal.signal_type,
            platform_max_volume=settings.MAX_LIVE_ORDER_VOLUME
        )
        if sizing.blocked:
            raise ExecutionError(f"Position sizing blocked: {sizing.block_reason}")
        actual_risk_amount = sizing.final_volume * sizing.loss_per_lot
        effective_risk_percent = (actual_risk_amount / equity * 100.0) if equity > 0 else 0.0

        # Risk Engine Enforcement
        open_trade_count = db.query(models.Trade).filter(
            models.Trade.user_id == user.id,
            models.Trade.status == models.TradeStatus.OPEN,
        ).count()
        daily_loss = _get_daily_loss(db, user.id)

        margin_result = {"requiredMargin": 0.0, "freeMarginAfterTrade": free_margin}
        if execution_mode in ("broker_demo", "live"):
            try:
                margin_result = metaapi.calculate_margin(
                    account.metaapi_account_id,
                    broker_symbol,
                    signal.signal_type,
                    sizing.final_volume,
                    observed_price,
                )
            except Exception as exc:
                raise ExecutionError(f"Broker margin calculation failed: {exc}") from exc
            required_margin = float(margin_result.get("requiredMargin") or 0.0)
            free_after_trade = free_margin - required_margin
            reserve_percent = float(getattr(settings, "FREE_MARGIN_RESERVE_PERCENT", 10.0))
            reserve_amount = equity * reserve_percent / 100.0
            margin_result["freeMarginAfterTrade"] = free_after_trade
            if required_margin <= 0:
                raise ExecutionError("Broker margin calculation returned zero or invalid required margin.")
            if required_margin > free_margin:
                raise ExecutionError(
                    f"Insufficient free margin. Required margin {required_margin:.2f}, current free margin {free_margin:.2f}."
                )
            if free_after_trade < reserve_amount:
                raise ExecutionError(
                    f"Free margin after trade {free_after_trade:.2f} would be below reserve {reserve_amount:.2f}."
                )

        quote_time_str = quote.get("time") or quote.get("brokerTime")
        risk_result = run_risk_checks(
            db=db,
            signal=signal,
            user=user,
            account=account,
            observed_price=observed_price,
            volume=sizing.final_volume,
            execution_mode=execution_mode,
            quote=quote,
            quote_time_str=quote_time_str,
            open_trade_count=open_trade_count,
            daily_realized_pnl=daily_loss,
            equity=equity,
            balance=metrics.balance,
            free_margin=free_margin,
            current_margin=metrics.margin,
            required_margin=float(margin_result.get("requiredMargin") or 0.0),
            free_margin_after_trade=float(margin_result.get("freeMarginAfterTrade") or free_margin),
            effective_risk_percent=effective_risk_percent,
            symbol=broker_symbol,
            symbol_point=spec.tick_size,
            is_jump_in=is_jump_in,
        )
        if not risk_result.approved:
            raise ExecutionError(f"Risk Engine rejected trade: {'; '.join(risk_result.reasons)}")

        # Create ExecutionIntent (idempotency guard)
        client_order_id = make_broker_client_id(signal.id)
        internal_execution_uuid = str(uuid4())
        intent = models.ExecutionIntent(
            user_id=user.id,
            signal_id=signal.id,
            broker_account_id=account.id,
            execution_mode=execution_mode,
            client_order_id=client_order_id,
            requested_volume=sizing.final_volume,
            requested_price=observed_price,
            equity_at_time=equity,
            risk_percent_at_time=risk_percent,
            tick_size_at_time=spec.tick_size,
            tick_value_at_time=spec.loss_tick_value,
            stop_loss_distance=sizing.stop_loss_distance,
            loss_per_lot=sizing.loss_per_lot,
            raw_volume=sizing.raw_volume,
            request_payload={
                "internal_execution_uuid": internal_execution_uuid,
                "broker_symbol": broker_symbol,
                "requested_risk_percent": risk_percent,
                "effective_risk_percent": effective_risk_percent,
                "risk_amount": actual_risk_amount,
                "account_metrics_source": "simulation" if metrics.is_simulated else "metaapi",
                "account_margin": metrics.margin,
                "account_balance": metrics.balance,
                "margin": margin_result,
                "live_account_verification": live_verification.__dict__ if live_verification else None,
            },
            status="CREATED",
        )
        db.add(intent)
        db.commit()
        db.refresh(intent)

        # -------------------------------------------------------------------
        # EXECUTION: PAPER
        # -------------------------------------------------------------------
        if execution_mode == "paper":
            intent.status = "FILLED"; intent.execution_state = "FILLED"
            intent.broker_order_id = f"paper-{uuid4()}"
            intent.broker_position_id = f"paper-pos-{uuid4()}"
            
            trade = models.Trade(
                user_id=user.id,
                signal_id=signal.id,
                broker_account_id=account.id,
                symbol=signal.symbol,
                broker_symbol=broker_symbol,
                trade_type=signal.signal_type,
                entry_price=observed_price,
                entry_time=utc_now(),
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit_1,
                volume=sizing.final_volume,
                status=models.TradeStatus.OPEN,
                mode=models.TradingMode.DEMO,
                execution_mode="paper",
                provider="paper",
                execution_intent_id=intent.id,
                client_order_id=client_order_id,
                broker_order_id=intent.broker_order_id,
                broker_position_id=intent.broker_position_id,
                requested_price=observed_price,
                actual_fill_price=observed_price,
                requested_volume=sizing.final_volume,
                actual_volume=sizing.final_volume,
                opened_time=utc_now(),
                reconciliation_status="reconciled",
                execution_status="filled",
            )
            db.add(trade)
            signal.status = models.SignalStatus.EXECUTED_DEMO
            signal.executed_at = utc_now()
            db.commit()
            db.refresh(trade)
            return trade

        # -------------------------------------------------------------------
        # EXECUTION: BROKER DEMO / LIVE (MetaApi Order Submission)
        # -------------------------------------------------------------------
        intent.status = "SUBMITTING"; intent.execution_state = "SUBMITTING"
        db.commit()

        comment = f"AT-{signal.id}"
        try:
            order_result = metaapi.place_market_order(
                metaapi_account_id=account.metaapi_account_id,
                symbol=broker_symbol,
                direction=signal.signal_type,
                volume=sizing.final_volume,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit_1,
                client_id=client_order_id,
                comment=comment,
            )

            intent.broker_order_id = str(order_result.get("orderId") or "")
            intent.broker_position_id = str(order_result.get("positionId") or "")
            intent.broker_deal_id = str(order_result.get("dealId") or "")
            intent.broker_response = order_result

            if not intent.broker_position_id:
                confirmed = _find_confirmed_position(
                    account,
                    client_order_id=client_order_id,
                    comment=comment,
                )
                if confirmed:
                    intent.broker_order_id = confirmed[0] or intent.broker_order_id
                    intent.broker_position_id = confirmed[1]
                    intent.broker_deal_id = confirmed[2] or intent.broker_deal_id

            if not intent.broker_position_id:
                intent.status = "SUBMITTING"; intent.execution_state = "SUBMITTING"
                intent.error = (
                    "Broker accepted the order, but MetaApi has not confirmed the "
                    "open position ID yet. Reconciliation is pending."
                )
                db.commit()
                raise ExecutionError(intent.error)

            intent.status = "FILLED"; intent.execution_state = "FILLED"
            db.commit()

            fill_price = float(order_result.get("openPrice") or observed_price)

            trade = models.Trade(
                user_id=user.id,
                signal_id=signal.id,
                broker_account_id=account.id,
                symbol=signal.symbol,
                broker_symbol=broker_symbol,
                trade_type=signal.signal_type,
                entry_price=fill_price,
                entry_time=utc_now(),
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit_1,
                volume=sizing.final_volume,
                status=models.TradeStatus.OPEN,
                mode=models.TradingMode.LIVE if execution_mode == "live" else models.TradingMode.DEMO,
                execution_mode=execution_mode,
                provider="metaapi",
                execution_intent_id=intent.id,
                client_order_id=client_order_id,
                broker_order_id=intent.broker_order_id,
                broker_position_id=intent.broker_position_id,
                broker_deal_id=intent.broker_deal_id,
                requested_price=observed_price,
                actual_fill_price=fill_price,
                requested_volume=sizing.final_volume,
                actual_volume=sizing.final_volume,
                opened_time=utc_now(),
                reconciliation_status="pending",
                execution_status="filled",
            )
            db.add(trade)

            signal.status = models.SignalStatus.EXECUTED_LIVE if execution_mode == "live" else models.SignalStatus.EXECUTED_DEMO
            signal.executed_at = utc_now()
            db.commit()
            db.refresh(trade)
            return trade

        except Exception as exc:
            # Idempotency recovery
            intent.status = "UNCERTAIN"; intent.execution_state = "UNCERTAIN"
            intent.error = str(exc)
            db.commit()

            logger.warning("Submission exception, querying account state to recover client ID: %s", client_order_id)
            try:
                confirmed = _find_confirmed_position(
                    account,
                    client_order_id=client_order_id,
                    comment=comment,
                )
                if confirmed:
                    intent.status = "FILLED"; intent.execution_state = "FILLED"
                    intent.broker_order_id = confirmed[0] or intent.broker_order_id
                    intent.broker_position_id = confirmed[1]
                    intent.broker_deal_id = confirmed[2] or intent.broker_deal_id
                    db.commit()

                if intent.status == "FILLED":
                    # Create the local trade record
                    trade = models.Trade(
                        user_id=user.id,
                        signal_id=signal.id,
                        broker_account_id=account.id,
                        symbol=signal.symbol,
                        broker_symbol=broker_symbol,
                        trade_type=signal.signal_type,
                        entry_price=observed_price,
                        entry_time=utc_now(),
                        stop_loss=signal.stop_loss,
                        take_profit=signal.take_profit_1,
                        volume=sizing.final_volume,
                        status=models.TradeStatus.OPEN,
                        mode=models.TradingMode.LIVE if execution_mode == "live" else models.TradingMode.DEMO,
                        execution_mode=execution_mode,
                        provider="metaapi",
                        execution_intent_id=intent.id,
                        client_order_id=client_order_id,
                        broker_order_id=intent.broker_order_id,
                        broker_position_id=intent.broker_position_id,
                        broker_deal_id=intent.broker_deal_id,
                        requested_price=observed_price,
                        actual_fill_price=observed_price,
                        requested_volume=sizing.final_volume,
                        actual_volume=sizing.final_volume,
                        opened_time=utc_now(),
                        reconciliation_status="pending",
                        execution_status="filled",
                    )
                    db.add(trade)
                    signal.status = models.SignalStatus.EXECUTED_LIVE if execution_mode == "live" else models.SignalStatus.EXECUTED_DEMO
                    signal.executed_at = utc_now()
                    db.commit()
                    db.refresh(trade)
                    return trade
                else:
                    intent.status = "REJECTED"; intent.execution_state = "REJECTED"
                    db.commit()
                    raise exc

            except Exception as recovery_exc:
                logger.error("Failed idempotency recovery: %s", recovery_exc)
                raise exc

    finally:
        lock.release()
