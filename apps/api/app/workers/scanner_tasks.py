"""Scanner Celery tasks.

These tasks are scheduled by Celery Beat to run on every closed candle.
Each task handles one (scanner_profile, symbol, timeframe) combination.
"""

from __future__ import annotations

import logging
from datetime import datetime, UTC
from typing import Optional

from app.workers import celery_app
from app.database import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.scanner_tasks.run_all_scanner_profiles",
    bind=True,
    max_retries=0,
    ignore_result=True,
)
def run_all_scanner_profiles(self):
    """
    Main scheduled scanner task.

    Runs once every SCANNER_DEFAULT_INTERVAL_SECONDS.
    Iterates all active ScannerProfiles across all users, fetches candles
    from the broker account, and calls the scanner pipeline.
    """
    from app import models
    from app.config import settings
    from app.services.metaapi_gateway import (
        get_candles, get_symbol_price, normalize_timeframe,
        extract_observed_price, MetaApiError,
    )
    from app.services.scanner.pipeline import run_scanner_pipeline
    from app.services.scanner.indicators import spread_in_points
    from app.services.broker_symbol_sync import needs_symbol_sync, sync_broker_symbols_for_account

    if not settings.SCANNER_ENABLED:
        return

    db = SessionLocal()
    try:
        # Load all enabled scanner profiles with active accounts
        profiles = (
            db.query(models.ScannerProfile)
            .filter(
                models.ScannerProfile.scan_enabled == True,  # noqa: E712
            )
            .all()
        )

        logger.info("Scanner: running %d active profiles", len(profiles))

        for profile in profiles:
            try:
                _scan_profile(db, profile)
            except Exception as exc:
                logger.error(
                    "Scanner error for profile %d: %s", profile.id, exc, exc_info=True
                )
    finally:
        db.close()


def _scan_profile(db, profile):
    """Process one ScannerProfile: iterate symbols × timeframes."""
    from app import models
    from app.services.metaapi_gateway import (
        get_candles, get_symbol_price, normalize_timeframe,
        extract_observed_price, MetaApiError,
    )
    from app.services.scanner.pipeline import run_scanner_pipeline
    from app.services.scanner.indicators import spread_in_points

    user = db.query(models.User).filter(models.User.id == profile.user_id).first()
    if not user or not user.is_active:
        return

    account = None
    if profile.broker_account_id:
        account = db.query(models.BrokerAccount).filter(
            models.BrokerAccount.id == profile.broker_account_id
        ).first()

    if not account or account.connection_state != "deployed" or not account.metaapi_account_id:
        logger.debug("Profile %d: broker account not ready", profile.id)
        return

    symbols = profile.symbols or []
    timeframes = profile.timeframes or ["H1"]

    if symbols and needs_symbol_sync(db, profile.broker_account_id, symbols):
        sync_result = sync_broker_symbols_for_account(db, account, preferred_symbols=symbols)
        if sync_result.synced:
            db.commit()

    # Build symbol → broker_symbol map from BrokerSymbol table
    broker_symbol_map = {}
    if symbols:
        broker_symbols_db = db.query(models.BrokerSymbol).filter(
            models.BrokerSymbol.broker_account_id == profile.broker_account_id,
            models.BrokerSymbol.canonical_symbol.in_(symbols),
            models.BrokerSymbol.trade_allowed == True,  # noqa: E712
        ).all()
        for bs in broker_symbols_db:
            broker_symbol_map[bs.canonical_symbol] = bs.broker_symbol

    for symbol in symbols:
        broker_sym = broker_symbol_map.get(symbol, symbol)

        try:
            # Get current quote
            quote = get_symbol_price(
                account.metaapi_account_id,
                broker_sym,
                require_fresh=True,
            )
        except MetaApiError as exc:
            logger.warning(
                "Profile %d: cannot get quote for %s: %s", profile.id, broker_sym, exc
            )
            continue

        bid = float(quote.get("bid") or quote.get("brokerBid") or 0)
        ask = float(quote.get("ask") or quote.get("brokerAsk") or 0)
        if bid <= 0 or ask <= 0:
            continue

        point = float(quote.get("point") or 0)
        sp = spread_in_points(bid, ask, point) if point > 0 else None

        for timeframe in timeframes:
            mt_tf = normalize_timeframe(timeframe)
            try:
                candles = get_candles(
                    account.metaapi_account_id, broker_sym, mt_tf, count=250
                )
            except MetaApiError as exc:
                logger.warning(
                    "Profile %d: cannot get candles for %s %s: %s",
                    profile.id, broker_sym, timeframe, exc,
                )
                continue

            if len(candles) < 50:
                logger.debug(
                    "Profile %d: insufficient candles for %s %s (%d)",
                    profile.id, symbol, timeframe, len(candles),
                )
                continue

            run_scanner_pipeline(
                db=db,
                scanner_profile=profile,
                candles=candles,
                symbol=symbol,
                broker_symbol=broker_sym,
                timeframe=timeframe,
                bid=bid,
                ask=ask,
                spread_points=sp,
                user=user,
            )


@celery_app.task(
    name="app.workers.scanner_tasks.run_single_profile",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def run_single_profile(self, scanner_profile_id: int):
    """
    Trigger an on-demand scan for a single scanner profile.
    Used by the API for manual trigger from the UI.
    """
    from app import models

    db = SessionLocal()
    try:
        profile = db.query(models.ScannerProfile).filter(
            models.ScannerProfile.id == scanner_profile_id
        ).first()
        if profile:
            _scan_profile(db, profile)
    except Exception as exc:
        logger.error("On-demand scan failed for profile %d: %s", scanner_profile_id, exc)
        raise self.retry(exc=exc)
    finally:
        db.close()
