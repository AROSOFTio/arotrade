"""Notification and signal expiry tasks."""

from __future__ import annotations

import logging
from datetime import datetime, UTC

from app.workers import celery_app
from app.database import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.notify_tasks.expire_stale_signals",
    bind=True,
    max_retries=0,
    ignore_result=True,
)
def expire_stale_signals(self):
    """
    Move past-their-valid_until approved signals to EXPIRED status.

    This prevents entry-zone monitoring from running indefinitely on old setups.
    """
    from app import models
    from app.services.notify import create_notification

    db = SessionLocal()
    try:
        now = datetime.now(UTC).replace(tzinfo=None)

        expiring = (
            db.query(models.Signal)
            .filter(
                models.Signal.status == models.SignalStatus.APPROVED,
                models.Signal.valid_until <= now,
                models.Signal.valid_until.isnot(None),
            )
            .all()
        )

        for signal in expiring:
            was_blocked = signal.lifecycle_status == models.SignalLifecycleStatus.BLOCKED.value
            signal.status = models.SignalStatus.EXPIRED
            signal.expired_at = now
            if hasattr(signal, "lifecycle_status") and not was_blocked:
                signal.lifecycle_status = models.SignalLifecycleStatus.EXPIRED.value

            if was_blocked and signal.blocked_reason:
                title = f"Signal expired after blocked execution: {signal.signal_type.upper()} {signal.symbol}"
                body = (
                    f"{signal.symbol} {signal.timeframe} {signal.signal_type.upper()} signal "
                    f"expired after execution was blocked: {signal.blocked_reason}"
                )
            else:
                title = f"Signal expired: {signal.signal_type.upper()} {signal.symbol}"
                body = (
                    f"{signal.symbol} {signal.timeframe} {signal.signal_type.upper()} signal "
                    f"has expired without being triggered. Entry zone was no longer valid."
                )

            create_notification(
                db,
                user_id=signal.user_id,
                title=title,
                body=body,
                category="signal",
                link=f"/dashboard/signals?signal={signal.id}",
            )

        if expiring:
            db.commit()
            logger.info("Expired %d stale signals", len(expiring))

    except Exception as exc:
        logger.error("expire_stale_signals failed: %s", exc, exc_info=True)
    finally:
        db.close()


@celery_app.task(
    name="app.workers.notify_tasks.check_entry_zones",
    bind=True,
    max_retries=0,
    ignore_result=True,
)
def check_entry_zones(self):
    """
    Check all approved signals: if price is now inside the entry zone,
    create a 'TRIGGERED' notification for the user.

    For profiles with approval_required=False, this could trigger auto-execution.
    For profiles with approval_required=True, it sends an alert to the user.
    """
    from app import models
    from app.config import settings
    from app.services.metaapi_gateway import get_symbol_price, MetaApiError
    from app.services.scanner.pipeline import check_entry_zone
    from app.services.notify import create_notification

    if not settings.SIGNAL_ENTRY_MONITOR_ENABLED:
        return

    db = SessionLocal()
    try:
        now = datetime.now(UTC).replace(tzinfo=None)

        approved_signals = (
            db.query(models.Signal)
            .filter(
                models.Signal.status == models.SignalStatus.APPROVED,
                models.Signal.valid_until > now,
            )
            .all()
        )

        if not approved_signals:
            return

        for signal in approved_signals:
            if not signal.broker_account_id or not signal.broker_symbol:
                continue

            account = db.query(models.BrokerAccount).filter(
                models.BrokerAccount.id == signal.broker_account_id
            ).first()
            if not account or account.connection_state != "deployed":
                continue

            try:
                quote = get_symbol_price(
                    account.metaapi_account_id,
                    signal.broker_symbol,
                    require_fresh=True,
                )
            except MetaApiError:
                continue

            bid = float(quote.get("bid") or 0)
            ask = float(quote.get("ask") or 0)

            if not check_entry_zone(signal, bid, ask):
                continue

            # Price is in entry zone — update lifecycle and notify
            mid = (bid + ask) / 2
            signal.latest_price = mid
            if signal.lifecycle_status != models.SignalLifecycleStatus.TRIGGERED.value:
                signal.lifecycle_status = models.SignalLifecycleStatus.TRIGGERED.value
                signal.triggered_at = now

                create_notification(
                    db,
                    user_id=signal.user_id,
                    title=f"🟢 Entry zone hit: {signal.signal_type.upper()} {signal.symbol}",
                    body=(
                        f"{signal.symbol} {signal.timeframe} {signal.signal_type.upper()} "
                        f"price {mid:.5f} is inside entry zone "
                        f"{signal.entry_min:.5f}–{signal.entry_max:.5f}."
                    ),
                    category="signal",
                    link=f"/dashboard/signals?signal={signal.id}",
                )

                logger.info(
                    "Signal %d triggered at price %.5f (entry zone %.5f–%.5f)",
                    signal.id, mid, signal.entry_min or 0, signal.entry_max or 0,
                )

                # Auto-execution check if approved and waiting for entry
                if signal.approved_action == "wait_for_entry" and signal.execution_mode:
                    from app.services.execution import execute_signal_trade
                    try:
                        logger.info("Auto-executing approved signal %d entering zone", signal.id)
                        signal.execution_started_at = now
                        signal.lifecycle_status = models.SignalLifecycleStatus.EXECUTION_PENDING.value
                        execute_signal_trade(
                            db,
                            user_id=signal.user_id,
                            signal_id=signal.id,
                            broker_account_id=signal.broker_account_id,
                            execution_mode=signal.execution_mode,
                            is_jump_in=False,
                        )
                    except Exception as e:
                        reason = str(e)
                        signal.blocked_reason = reason
                        signal.lifecycle_status = models.SignalLifecycleStatus.BLOCKED.value
                        db.add(models.ExecutionAudit(
                            user_id=signal.user_id,
                            signal_id=signal.id,
                            trade_id=None,
                            broker="metaapi" if signal.execution_mode in ("broker_demo", "live") else "paper",
                            mode=signal.execution_mode,
                            outcome="failed",
                            reason=reason,
                            details={
                                "source": "entry_zone_monitor",
                                "broker_account_id": signal.broker_account_id,
                                "broker_symbol": signal.broker_symbol,
                                "entry_min": signal.entry_min,
                                "entry_max": signal.entry_max,
                                "latest_price": mid,
                            },
                        ))
                        create_notification(
                            db,
                            user_id=signal.user_id,
                            title=f"Execution blocked: {signal.signal_type.upper()} {signal.symbol}",
                            body=(
                                f"{signal.symbol} {signal.timeframe} {signal.signal_type.upper()} "
                                f"hit the entry zone, but order execution was blocked: {reason}"
                            ),
                            category="signal",
                            link=f"/dashboard/signals?signal={signal.id}",
                        )
                        logger.error("Auto-execution of signal %d failed: %s", signal.id, e)

        db.commit()

    except Exception as exc:
        logger.error("check_entry_zones failed: %s", exc, exc_info=True)
    finally:
        db.close()
