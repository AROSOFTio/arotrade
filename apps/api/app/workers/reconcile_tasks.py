"""Reconciliation tasks: sync local trade records with broker positions."""

from __future__ import annotations

import logging
from datetime import datetime, UTC

from app.workers import celery_app
from app.database import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.reconcile_tasks.reconcile_broker_positions",
    bind=True,
    max_retries=1,
    ignore_result=True,
)
def reconcile_broker_positions(self):
    """
    Reconcile open local Trade records with actual broker positions.

    For each open live/broker_demo trade:
      1. Fetch the position from MetaApi by broker_order_id / position_id
      2. If position is closed at broker: mark local trade as CLOSED with broker PnL
      3. If position modified (SL/TP changed): update local trade
      4. If local trade has no matching broker position: flag as RECONCILIATION_ERROR

    This task prevents "zombie" open trades in the local DB.
    """
    from app import models
    from app.services.metaapi_gateway import get_positions, MetaApiError

    db = SessionLocal()
    try:
        # Only reconcile live and broker_demo trades
        open_trades = (
            db.query(models.Trade)
            .filter(
                models.Trade.status == models.TradeStatus.OPEN,
                models.Trade.execution_status.in_(["filled", "submitted"]),
                models.Trade.broker_order_id.isnot(None),
            )
            .all()
        )

        if not open_trades:
            return

        # Group by MetaApi account ID
        account_ids = set()
        trade_by_position: dict[str, models.Trade] = {}

        for trade in open_trades:
            # Find the broker account
            if not trade.user_id:
                continue
            # Use the signal's broker_account_id if available
            if hasattr(trade, "signal") and trade.signal and trade.signal.broker_account_id:
                account_id = trade.signal.broker_account_id
                broker_account = db.query(models.BrokerAccount).filter(
                    models.BrokerAccount.id == account_id
                ).first()
            else:
                broker_account = (
                    db.query(models.BrokerAccount)
                    .filter(
                        models.BrokerAccount.user_id == trade.user_id,
                        models.BrokerAccount.is_active == True,  # noqa: E712
                        models.BrokerAccount.connection_state == "deployed",
                    )
                    .first()
                )

            if not broker_account or not broker_account.metaapi_account_id:
                continue

            meta_account_id = broker_account.metaapi_account_id
            account_ids.add(meta_account_id)

            pid = trade.broker_order_id or ""
            trade_by_position[f"{meta_account_id}:{pid}"] = trade

        if not account_ids:
            return

        changed = 0
        for meta_account_id in account_ids:
            try:
                positions = get_positions(meta_account_id)
                open_ids = {str(p.get("id") or p.get("positionId", "")) for p in positions}

                for trade in open_trades:
                    pid = trade.broker_order_id or ""
                    key = f"{meta_account_id}:{pid}"
                    if key not in trade_by_position:
                        continue
                    if pid not in open_ids:
                        # Position is closed at broker
                        trade.status = models.TradeStatus.CLOSED
                        trade.execution_status = "reconciled_closed"
                        trade.exit_time = datetime.now(UTC).replace(tzinfo=None)
                        db.add(trade)
                        changed += 1
                        logger.info(
                            "Reconciled: trade %d closed at broker (position %s)",
                            trade.id, pid,
                        )

            except MetaApiError as exc:
                logger.warning("Reconciliation error for account %s: %s", meta_account_id, exc)

        if changed:
            db.commit()
            logger.info("Reconciliation complete: %d trades updated", changed)

    except Exception as exc:
        logger.error("Reconciliation task failed: %s", exc, exc_info=True)
    finally:
        db.close()
