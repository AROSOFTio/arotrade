"""Unified order execution service for manual trades.

This module provides preview and execute operations for manual market
orders that do not originate from a Signal.  It reuses the same risk
engine, position sizing, margin checks, and MetaApi gateway used by
signal-based execution.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, UTC
from secrets import token_hex
from typing import Optional
from uuid import uuid4

import redis
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.services import metaapi_gateway as metaapi
from app.services.execution import (
    BrokerAccountMetrics,
    ExecutionError,
    _find_confirmed_position,
    get_broker_account_metrics,
    resolve_broker_symbol,
    utc_now,
    verify_live_broker_account,
)
from app.services.position_sizing import calculate_position_size, spec_from_metaapi_specification
from app.services.risk_engine import RiskCheckResult, run_risk_checks
from app.services import trading_control

logger = logging.getLogger(__name__)
redis_client = redis.Redis.from_url(settings.REDIS_URL)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _manual_client_id() -> str:
    return f"MT{token_hex(6).upper()}"


def _auto_renewing_lock(lock, interval: float = 8.0, timeout: float = 30.0):
    """Daemon thread that extends a Redis lock periodically."""
    stop = threading.Event()

    def _renew():
        while not stop.is_set():
            try:
                lock.extend(timeout)
            except Exception:
                break
            stop.wait(interval)

    t = threading.Thread(target=_renew, daemon=True)
    t.start()
    return stop


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

def preview_manual_order(
    db: Session,
    *,
    user_id: int,
    broker_account_id: int,
    symbol: str,
    direction: str,
    stop_loss: float,
    take_profit: Optional[float],
    volume: Optional[float],
    risk_percent: Optional[float],
) -> dict:
    """Compute everything needed for the trade ticket preview."""

    user = db.query(models.User).filter(models.User.id == user_id).first()
    account = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.id == broker_account_id,
        models.BrokerAccount.user_id == user_id,
        models.BrokerAccount.is_active == True,  # noqa: E712
    ).first()
    if not user or not account:
        raise ExecutionError("User or broker account not found.")

    broker_symbol = resolve_broker_symbol(db, symbol, account)

    # Quote and spec
    quote = metaapi.get_symbol_price(account.metaapi_account_id, broker_symbol, require_fresh=False)
    spec_dict = metaapi.get_symbol_specification(account.metaapi_account_id, broker_symbol)
    spec = spec_from_metaapi_specification(spec_dict, quote)
    if not spec:
        raise ExecutionError(f"Incomplete broker specifications for {broker_symbol}.")

    observed_price = metaapi.extract_observed_price(quote, direction)
    if observed_price <= 0:
        raise ExecutionError("Observed price is invalid.")

    bid = float(quote.get("bid") or 0)
    ask = float(quote.get("ask") or 0)
    spread = ask - bid if ask and bid else 0.0

    # Determine execution mode from account type
    acct_type = getattr(account.account_type, "value", str(account.account_type))
    execution_mode = "live" if acct_type == "live" else "broker_demo"

    metrics = get_broker_account_metrics(account, execution_mode)

    # Sizing
    rp = risk_percent or user.default_risk_percent
    if volume:
        final_volume = volume
        risk_amount = abs(observed_price - stop_loss) * volume * (spec.loss_tick_value / spec.tick_size if spec.tick_size else 1)
    else:
        sizing = calculate_position_size(
            equity=metrics.equity,
            risk_percent=rp,
            entry_price=observed_price,
            stop_loss=stop_loss,
            spec=spec,
            direction=direction,
            platform_max_volume=settings.MAX_LIVE_ORDER_VOLUME,
        )
        if sizing.blocked:
            raise ExecutionError(f"Position sizing blocked: {sizing.block_reason}")
        final_volume = sizing.final_volume
        risk_amount = sizing.risk_amount

    # Margin
    margin_result = {"requiredMargin": 0.0}
    try:
        margin_result = metaapi.calculate_margin(
            account.metaapi_account_id, broker_symbol, direction, final_volume, observed_price,
        )
    except Exception:
        pass
    required_margin = float(margin_result.get("requiredMargin") or 0.0)
    free_margin_after = metrics.free_margin - required_margin

    # Quote age
    quote_time_str = quote.get("time") or quote.get("brokerTime")
    quote_age = None
    stale = False
    if quote_time_str:
        try:
            qt = datetime.fromisoformat(str(quote_time_str).replace("Z", "+00:00"))
            quote_age = (datetime.now(UTC) - qt).total_seconds()
            stale = quote_age > settings.QUOTE_STALE_AFTER_SECONDS
        except Exception:
            pass

    # Risk warnings (advisory, non-blocking)
    risk_warnings = []
    # Calculate open trade count
    open_trade_count = db.query(models.Trade).filter(
        models.Trade.user_id == user.id,
        models.Trade.status == models.TradeStatus.OPEN,
    ).count()
    # Calculate daily loss
    from app.services.execution import _get_daily_loss
    daily_loss = _get_daily_loss(db, user.id)

    risk_result = run_risk_checks(
        db=db, user=user, account=account, observed_price=observed_price,
        volume=final_volume, execution_mode=execution_mode, quote=quote,
        stop_loss=stop_loss, quote_time_str=quote_time_str,
        open_trade_count=open_trade_count, daily_realized_pnl=daily_loss,
        equity=metrics.equity, free_margin=metrics.free_margin,
        required_margin=required_margin,
        free_margin_after_trade=free_margin_after,
    )
    if not risk_result.approved:
        risk_warnings = risk_result.reasons

    return {
        "broker_symbol": broker_symbol,
        "direction": direction,
        "bid": bid,
        "ask": ask,
        "spread": round(spread, 6),
        "observed_price": observed_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "calculated_volume": final_volume,
        "risk_amount": round(risk_amount, 2),
        "required_margin": round(required_margin, 2),
        "free_margin_after": round(free_margin_after, 2),
        "equity": round(metrics.equity, 2),
        "balance": round(metrics.balance, 2),
        "account_currency": str(account.currency or "USD"),
        "quote_time": quote_time_str,
        "quote_age_seconds": round(quote_age, 1) if quote_age is not None else None,
        "stale_data_warning": stale,
        "risk_warnings": risk_warnings,
    }


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------

def execute_manual_order(
    db: Session,
    *,
    user_id: int,
    broker_account_id: int,
    symbol: str,
    direction: str,
    stop_loss: float,
    take_profit: Optional[float],
    volume: Optional[float],
    risk_percent: Optional[float],
    idempotency_key: str,
) -> models.Trade:
    """Execute a manual market order with full risk/safety/idempotency pipeline."""

    if direction not in ("buy", "sell"):
        raise ExecutionError("Direction must be 'buy' or 'sell'.")

    # Idempotency check
    existing_intent = db.query(models.ExecutionIntent).filter(
        models.ExecutionIntent.idempotency_key == idempotency_key,
    ).first()
    if existing_intent:
        existing_trade = db.query(models.Trade).filter(
            models.Trade.execution_intent_id == existing_intent.id,
        ).first()
        if existing_trade:
            return existing_trade
        raise ExecutionError(f"Execution intent already exists with status {existing_intent.status}.")

    # Distributed lock with auto-renewal
    lock_key = f"lock:manual:execute:{idempotency_key}"
    lock = redis_client.lock(lock_key, timeout=30)
    if not lock.acquire(blocking=True, blocking_timeout=10):
        raise ExecutionError("Could not acquire execution lock.")

    stop_renewal = _auto_renewing_lock(lock)
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        account = db.query(models.BrokerAccount).filter(
            models.BrokerAccount.id == broker_account_id,
            models.BrokerAccount.user_id == user_id,
            models.BrokerAccount.is_active == True,  # noqa: E712
        ).first()
        if not user or not account:
            raise ExecutionError("User or broker account not found.")

        # Determine execution mode
        acct_type = getattr(account.account_type, "value", str(account.account_type))
        execution_mode = "live" if acct_type == "live" else "broker_demo"

        broker_symbol = resolve_broker_symbol(db, symbol, account)

        # Live account verification
        live_verification = verify_live_broker_account(account) if execution_mode == "live" else None

        # Quote & spec
        quote = metaapi.get_symbol_price(account.metaapi_account_id, broker_symbol, require_fresh=True)
        spec_dict = metaapi.get_symbol_specification(account.metaapi_account_id, broker_symbol)
        spec = spec_from_metaapi_specification(spec_dict, quote)
        if not spec:
            raise ExecutionError(f"Incomplete broker specifications for {broker_symbol}.")

        observed_price = metaapi.extract_observed_price(quote, direction)
        if observed_price <= 0:
            raise ExecutionError("Observed price is invalid.")

        metrics = get_broker_account_metrics(account, execution_mode)

        # Sizing
        rp = risk_percent or user.default_risk_percent
        if volume:
            final_volume = volume
        else:
            sizing = calculate_position_size(
                equity=metrics.equity, risk_percent=rp,
                entry_price=observed_price, stop_loss=stop_loss,
                spec=spec, direction=direction,
                platform_max_volume=settings.MAX_LIVE_ORDER_VOLUME,
            )
            if sizing.blocked:
                raise ExecutionError(f"Position sizing blocked: {sizing.block_reason}")
            final_volume = sizing.final_volume

        # Margin
        margin_result = {"requiredMargin": 0.0, "freeMarginAfterTrade": metrics.free_margin}
        try:
            margin_result = metaapi.calculate_margin(
                account.metaapi_account_id, broker_symbol, direction, final_volume, observed_price,
            )
        except Exception as exc:
            raise ExecutionError(f"Broker margin calculation failed: {exc}") from exc
        required_margin = float(margin_result.get("requiredMargin") or 0.0)
        free_margin_after = metrics.free_margin - required_margin

        # Risk checks
        open_trade_count = db.query(models.Trade).filter(
            models.Trade.user_id == user.id,
            models.Trade.status == models.TradeStatus.OPEN,
        ).count()
        from app.services.execution import _get_daily_loss
        daily_loss = _get_daily_loss(db, user.id)
        quote_time_str = quote.get("time") or quote.get("brokerTime")

        risk_result = run_risk_checks(
            db=db, user=user, account=account, observed_price=observed_price,
            volume=final_volume, execution_mode=execution_mode, quote=quote,
            stop_loss=stop_loss, quote_time_str=quote_time_str,
            open_trade_count=open_trade_count, daily_realized_pnl=daily_loss,
            equity=metrics.equity, free_margin=metrics.free_margin,
            required_margin=required_margin,
            free_margin_after_trade=free_margin_after,
        )
        if not risk_result.approved:
            raise ExecutionError(f"Risk engine rejected: {'; '.join(risk_result.reasons)}")

        # Create ExecutionIntent
        client_order_id = _manual_client_id()
        intent = models.ExecutionIntent(
            user_id=user.id,
            signal_id=None,
            broker_account_id=account.id,
            execution_mode=execution_mode,
            idempotency_key=idempotency_key,
            client_order_id=client_order_id,
            requested_volume=final_volume,
            requested_price=observed_price,
            equity_at_time=metrics.equity,
            risk_percent_at_time=rp,
            tick_size_at_time=spec.tick_size,
            tick_value_at_time=spec.loss_tick_value,
            request_payload={
                "manual_order": True,
                "broker_symbol": broker_symbol,
                "direction": direction,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            },
            status="CREATED",
        )
        db.add(intent)
        db.commit()
        db.refresh(intent)

        # Submit to broker
        intent.status = "SUBMITTING"
        intent.execution_state = "SUBMITTING"
        db.commit()

        comment = f"MT-{client_order_id[:8]}"
        try:
            order_result = metaapi.place_market_order(
                metaapi_account_id=account.metaapi_account_id,
                symbol=broker_symbol,
                direction=direction,
                volume=final_volume,
                stop_loss=stop_loss,
                take_profit=take_profit,
                client_id=client_order_id,
                comment=comment,
            )

            intent.broker_order_id = str(order_result.get("orderId") or "")
            intent.broker_position_id = str(order_result.get("positionId") or "")
            intent.broker_deal_id = str(order_result.get("dealId") or "")
            intent.broker_response = order_result

            if not intent.broker_position_id:
                confirmed = _find_confirmed_position(
                    account, client_order_id=client_order_id, comment=comment,
                )
                if confirmed:
                    intent.broker_order_id = confirmed[0] or intent.broker_order_id
                    intent.broker_position_id = confirmed[1]
                    intent.broker_deal_id = confirmed[2] or intent.broker_deal_id

            if not intent.broker_position_id:
                intent.status = "UNCERTAIN"
                intent.execution_state = "UNCERTAIN"
                intent.error = "Broker accepted order but position ID not confirmed yet."
                db.commit()
                raise ExecutionError(intent.error)

            intent.status = "FILLED"
            intent.execution_state = "FILLED"
            db.commit()

            fill_price = float(order_result.get("openPrice") or observed_price)

            trade = models.Trade(
                user_id=user.id,
                signal_id=None,
                broker_account_id=account.id,
                symbol=symbol.upper(),
                broker_symbol=broker_symbol,
                trade_type=direction,
                entry_price=fill_price,
                entry_time=utc_now(),
                stop_loss=stop_loss,
                take_profit=take_profit,
                volume=final_volume,
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
                requested_volume=final_volume,
                actual_volume=final_volume,
                opened_time=utc_now(),
                reconciliation_status="pending",
                execution_status="filled",
            )
            db.add(trade)
            db.commit()
            db.refresh(trade)
            return trade

        except ExecutionError:
            raise
        except Exception as exc:
            intent.status = "UNCERTAIN"
            intent.execution_state = "UNCERTAIN"
            intent.error = str(exc)
            db.commit()

            # Idempotency recovery
            try:
                confirmed = _find_confirmed_position(
                    account, client_order_id=client_order_id, comment=comment,
                )
                if confirmed:
                    intent.status = "FILLED"
                    intent.execution_state = "FILLED"
                    intent.broker_order_id = confirmed[0] or intent.broker_order_id
                    intent.broker_position_id = confirmed[1]
                    intent.broker_deal_id = confirmed[2] or intent.broker_deal_id
                    db.commit()

                    trade = models.Trade(
                        user_id=user.id,
                        signal_id=None,
                        broker_account_id=account.id,
                        symbol=symbol.upper(),
                        broker_symbol=broker_symbol,
                        trade_type=direction,
                        entry_price=observed_price,
                        entry_time=utc_now(),
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        volume=final_volume,
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
                        requested_volume=final_volume,
                        actual_volume=final_volume,
                        opened_time=utc_now(),
                        reconciliation_status="pending",
                        execution_status="filled",
                    )
                    db.add(trade)
                    db.commit()
                    db.refresh(trade)
                    return trade
                else:
                    intent.status = "REJECTED"
                    intent.execution_state = "REJECTED"
                    db.commit()
                    raise exc
            except ExecutionError:
                raise
            except Exception:
                raise exc

    finally:
        stop_renewal.set()
        try:
            lock.release()
        except Exception:
            pass


def reconcile_account(account_id: int, user_id: int, db: Session) -> dict:
    """Sync position and order history from MetaApi for a specific account."""
    account = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.id == account_id,
        models.BrokerAccount.user_id == user_id,
    ).first()
    if not account:
        raise ExecutionError("Broker account not found.")

    if not account.metaapi_account_id or account.connection_state != "deployed":
        return {"status": "skipped", "reason": "Account not deployed or not connected."}

    # Fetch all open trades for this account
    trades = db.query(models.Trade).filter(
        models.Trade.broker_account_id == account.id,
        models.Trade.status == models.TradeStatus.OPEN,
    ).all()

    reconciled_count = 0
    modified_count = 0
    uncertain_count = 0

    try:
        positions = metaapi.get_positions(account.metaapi_account_id)
        history_deals = metaapi.get_history_orders(account.metaapi_account_id)

        for trade in trades:
            # Try to match open position
            matched_pos = None
            for pos in positions:
                if str(pos.get("id") or pos.get("positionId") or "") == str(trade.broker_position_id):
                    matched_pos = pos
                    break

            if matched_pos:
                sl = float(matched_pos.get("stopLoss") or 0.0)
                tp = float(matched_pos.get("takeProfit") or 0.0)
                vol = float(matched_pos.get("volume") or 0.0)
                
                updated = False
                if sl > 0 and abs(trade.stop_loss - sl) > 1e-6:
                    trade.stop_loss = sl
                    updated = True
                if tp > 0 and abs((trade.take_profit or 0.0) - tp) > 1e-6:
                    trade.take_profit = tp
                    updated = True
                if vol > 0 and abs(trade.actual_volume - vol) > 1e-6:
                    trade.actual_volume = vol
                    updated = True
                
                if updated:
                    trade.reconciliation_status = "modified"
                    db.add(trade)
                    modified_count += 1
            else:
                # Search historical deals
                closing_deal = None
                for deal in history_deals:
                    if str(deal.get("positionId") or "") == str(trade.broker_position_id) and deal.get("entryType") == "DEAL_ENTRY_OUT":
                        closing_deal = deal
                        break

                if closing_deal:
                    trade.status = models.TradeStatus.CLOSED
                    trade.exit_price = float(closing_deal.get("price") or trade.exit_price or 0.0)
                    trade.exit_time = utc_now()
                    trade.broker_profit = float(closing_deal.get("profit") or 0.0)
                    trade.profit_loss = trade.broker_profit
                    trade.commission = float(closing_deal.get("commission") or 0.0)
                    trade.swap = float(closing_deal.get("swap") or 0.0)
                    trade.reconciliation_status = "reconciled"
                    trade.execution_status = "reconciled_closed"
                    db.add(trade)
                    reconciled_count += 1
                else:
                    trade.reconciliation_status = "uncertain_closed"
                    db.add(trade)
                    uncertain_count += 1

        db.commit()
    except Exception as exc:
        raise ExecutionError(f"Reconciliation error: {exc}")

    return {
        "status": "success",
        "reconciled": reconciled_count,
        "modified": modified_count,
        "uncertain": uncertain_count,
    }
