"""Reconciliation tasks: sync local trade records with broker positions."""

from __future__ import annotations

import logging
from datetime import datetime, UTC

from app.workers import celery_app
from app.database import SessionLocal

logger = logging.getLogger(__name__)

def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)

@celery_app.task(
    name="app.workers.reconcile_tasks.reconcile_broker_positions",
    bind=True,
    max_retries=1,
    ignore_result=True,
)
def reconcile_broker_positions(self):
    """
    Reconcile open local Trade records with actual broker positions.
    Enforces checks per exact broker_account_id on the trade, handles partial closes,
    modified SL/TP levels, and prevents marking closed during outages.
    """
    from app import models
    from app.services.metaapi_gateway import get_positions, get_history_orders, MetaApiError

    db = SessionLocal()
    try:
        # Reconcile broker-demo and live open trades
        open_trades = (
            db.query(models.Trade)
            .filter(
                models.Trade.status == models.TradeStatus.OPEN,
                models.Trade.execution_mode.in_(["broker_demo", "live"]),
            )
            .all()
        )

        if not open_trades:
            return

        for trade in open_trades:
            if not trade.broker_account_id:
                continue

            account = db.query(models.BrokerAccount).filter(
                models.BrokerAccount.id == trade.broker_account_id
            ).first()
            if not account or not account.metaapi_account_id or account.connection_state != "deployed":
                continue

            try:
                # 1. Fetch current open positions from MetaApi for the exact account
                positions = get_positions(account.metaapi_account_id)
                
                # Try to locate the position matching broker_position_id
                matched_pos = None
                for pos in positions:
                    if str(pos.get("id") or pos.get("positionId") or "") == str(trade.broker_position_id):
                        matched_pos = pos
                        break

                if matched_pos:
                    # Position is still open! Check if SL, TP or Volume changed
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
                        db.commit()
                        logger.info("Reconciled: trade %d modified in MT5", trade.id)
                else:
                    # Position not found in open positions — search history/deals to verify closure
                    history_deals = get_history_orders(account.metaapi_account_id)
                    
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
                        db.commit()
                        logger.info("Reconciled: trade %d closed in MT5", trade.id)
                    else:
                        # Position is closed but no historical deal found yet. Mark degraded but don't close.
                        trade.reconciliation_status = "uncertain_closed"
                        db.add(trade)
                        db.commit()

            except MetaApiError as exc:
                # Connection outage! Do NOT mark position as closed!
                logger.warning("Reconciliation MetaApi error for account %s: %s. Outage detected, skipping.", account.metaapi_account_id, exc)

    except Exception as exc:
        logger.error("Reconciliation task failed: %s", exc, exc_info=True)
    finally:
        db.close()
