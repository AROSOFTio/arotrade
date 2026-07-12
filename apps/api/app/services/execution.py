import logging
import redis
from datetime import datetime, UTC
from typing import Optional
from uuid import uuid4
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

def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)

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
    lock_key = f"lock:signal:execute:{signal_id}"
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

        # Database row lock on the signal
        signal = db.query(models.Signal).filter(models.Signal.id == signal_id).with_for_update().first()
        if not signal:
            raise ExecutionError("Signal not found.")

        # Safety Check: Duplicate trades or intents
        existing_trade = db.query(models.Trade).filter(
            models.Trade.signal_id == signal_id,
            models.Trade.status == models.TradeStatus.OPEN,
        ).first()
        if existing_trade:
            raise ExecutionError("Signal already has an open trade.")

        existing_intent = db.query(models.ExecutionIntent).filter(
            models.ExecutionIntent.signal_id == signal_id,
            models.ExecutionIntent.execution_mode == execution_mode,
            models.ExecutionIntent.status.in_(["pending", "submitted", "filled"]),
        ).first()
        if existing_intent:
            raise ExecutionError("Execution intent is already active for this signal.")

        # Get MT5 Quote and Specifications
        try:
            quote = metaapi.get_symbol_price(account.metaapi_account_id, signal.broker_symbol, require_fresh=True)
            spec_dict = metaapi.get_symbol_specification(account.metaapi_account_id, signal.broker_symbol)
        except Exception as exc:
            raise ExecutionError(f"Failed to fetch broker data for {signal.broker_symbol}: {exc}")

        spec = spec_from_metaapi_specification(spec_dict)
        if not spec:
            raise ExecutionError(f"Incomplete broker specifications for {signal.broker_symbol}.")

        # Retrieve Account Info from MetaApi REST/Client
        try:
            info = metaapi.get_account_information(account.metaapi_account_id)
            equity = float(info.get("equity") or account.balance or 10000)
            free_margin = float(info.get("freeMargin") or equity)
        except Exception:
            equity = float(account.balance or 10000)
            free_margin = equity

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
            free_margin=free_margin,
            direction=signal.signal_type,
            platform_max_volume=settings.MAX_LIVE_ORDER_VOLUME
        )
        if sizing.blocked:
            raise ExecutionError(f"Position sizing blocked: {sizing.block_reason}")

        # Risk Engine Enforcement
        open_trade_count = db.query(models.Trade).filter(
            models.Trade.user_id == user.id,
            models.Trade.status == models.TradeStatus.OPEN,
        ).count()
        daily_loss = _get_daily_loss(db, user.id)

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
            free_margin=free_margin,
            is_jump_in=is_jump_in,
        )
        if not risk_result.approved:
            raise ExecutionError(f"Risk Engine rejected trade: {'; '.join(risk_result.reasons)}")

        # Create ExecutionIntent (idempotency guard)
        client_order_id = f"arotrade-{execution_mode}-{uuid4()}"
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
            tick_value_at_time=spec.tick_value,
            stop_loss_distance=sizing.stop_loss_distance,
            loss_per_lot=sizing.loss_per_lot,
            raw_volume=sizing.raw_volume,
            status="pending",
        )
        db.add(intent)
        db.commit()
        db.refresh(intent)

        # -------------------------------------------------------------------
        # EXECUTION: PAPER
        # -------------------------------------------------------------------
        if execution_mode == "paper":
            intent.status = "filled"
            intent.broker_order_id = f"paper-{uuid4()}"
            intent.broker_position_id = f"paper-pos-{uuid4()}"
            
            trade = models.Trade(
                user_id=user.id,
                signal_id=signal.id,
                broker_account_id=account.id,
                symbol=signal.symbol,
                broker_symbol=signal.broker_symbol,
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
        intent.status = "submitted"
        db.commit()

        try:
            order_result = metaapi.place_market_order(
                metaapi_account_id=account.metaapi_account_id,
                symbol=signal.broker_symbol,
                direction=signal.signal_type,
                volume=sizing.final_volume,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit_1,
                client_id=client_order_id,
                comment=f"AroTrade #{signal.id}",
            )

            intent.status = "filled"
            intent.broker_order_id = str(order_result.get("orderId") or "")
            intent.broker_position_id = str(order_result.get("positionId") or order_result.get("orderId") or "")
            intent.broker_deal_id = str(order_result.get("dealId") or "")
            intent.broker_response = order_result
            db.commit()

            fill_price = float(order_result.get("openPrice") or observed_price)

            trade = models.Trade(
                user_id=user.id,
                signal_id=signal.id,
                broker_account_id=account.id,
                symbol=signal.symbol,
                broker_symbol=signal.broker_symbol,
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
            intent.status = "uncertain"
            intent.error = str(exc)
            db.commit()

            logger.warning("Submission exception, querying account state to recover client ID: %s", client_order_id)
            try:
                # 1. Query open positions
                positions = metaapi.get_positions(account.metaapi_account_id)
                for pos in positions:
                    if pos.get("clientId") == client_order_id or f"AroTrade #{signal_id}" in str(pos.get("comment", "")):
                        intent.status = "filled"
                        intent.broker_position_id = str(pos.get("id") or pos.get("positionId") or "")
                        intent.broker_order_id = str(pos.get("orderId") or "")
                        intent.broker_deal_id = str(pos.get("dealId") or "")
                        db.commit()
                        break

                if intent.status != "filled":
                    # 2. Query history orders/deals
                    history = metaapi.get_history_orders(account.metaapi_account_id)
                    for order in history:
                        if order.get("clientId") == client_order_id or f"AroTrade #{signal_id}" in str(order.get("comment", "")):
                            intent.status = "filled"
                            intent.broker_order_id = str(order.get("id") or "")
                            intent.broker_position_id = str(order.get("positionId") or "")
                            intent.broker_deal_id = str(order.get("dealId") or "")
                            db.commit()
                            break

                if intent.status == "filled":
                    # Create the local trade record
                    trade = models.Trade(
                        user_id=user.id,
                        signal_id=signal.id,
                        broker_account_id=account.id,
                        symbol=signal.symbol,
                        broker_symbol=signal.broker_symbol,
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
                    intent.status = "failed"
                    db.commit()
                    raise exc

            except Exception as recovery_exc:
                logger.error("Failed idempotency recovery: %s", recovery_exc)
                raise exc

    finally:
        lock.release()
