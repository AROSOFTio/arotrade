"""Broker symbol discovery and scanner bootstrap helpers."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app import models
from app.services import metaapi_gateway as metaapi

logger = logging.getLogger(__name__)

DEFAULT_SCAN_SYMBOL_PRIORITY = (
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
    "XAUUSD",
    "USDJPY",
    "AUDUSD",
    "US30",
)

KNOWN_CANONICAL_SYMBOLS = (
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "AUDUSD",
    "USDCAD",
    "USDCHF",
    "NZDUSD",
    "EURJPY",
    "GBPJPY",
    "XAUUSD",
    "XAGUSD",
    "BTCUSD",
    "ETHUSD",
    "US30",
    "NAS100",
    "SPX500",
)

SYMBOL_CATEGORIES = {
    "EURUSD": "forex",
    "GBPUSD": "forex",
    "USDJPY": "forex",
    "AUDUSD": "forex",
    "USDCAD": "forex",
    "USDCHF": "forex",
    "NZDUSD": "forex",
    "EURJPY": "forex",
    "GBPJPY": "forex",
    "XAUUSD": "metals",
    "XAGUSD": "metals",
    "BTCUSD": "crypto",
    "ETHUSD": "crypto",
    "US30": "indices",
    "NAS100": "indices",
    "SPX500": "indices",
}

ALLOWED_SUFFIXES = {
    "",
    "M",
    "R",
    "C",
    "Z",
    "PRO",
    "RAW",
    "ECN",
    "STD",
    "X10M",
}


@dataclass
class SymbolSyncResult:
    synced: int = 0
    skipped: int = 0
    error: Optional[str] = None


def _broker_symbol_name(raw: object) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        return str(raw.get("symbol") or raw.get("name") or "")
    return str(raw or "")


def _compact(symbol: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", symbol.upper())


def canonical_symbol_for_broker_symbol(broker_symbol: str) -> Optional[str]:
    compact = _compact(broker_symbol)
    if compact in {"GOLD", "GOLDM", "XAUSDM"}:
        return "XAUUSD"

    for canonical in sorted(KNOWN_CANONICAL_SYMBOLS, key=len, reverse=True):
        if compact == canonical:
            return canonical
        if compact.startswith(canonical):
            suffix = compact[len(canonical):]
            if suffix in ALLOWED_SUFFIXES:
                return canonical
    return None


def _spec_value(spec: dict, *keys: str):
    for key in keys:
        value = spec.get(key)
        if value is not None:
            return value
    return None


def needs_symbol_sync(
    db: Session,
    account_id: int,
    symbols: Optional[Iterable[str]] = None,
    *,
    max_age: timedelta = timedelta(hours=12),
) -> bool:
    query = db.query(models.BrokerSymbol).filter(
        models.BrokerSymbol.broker_account_id == account_id,
        models.BrokerSymbol.trade_allowed == True,  # noqa: E712
    )
    if symbols:
        wanted = [s.upper() for s in symbols]
        existing = query.filter(models.BrokerSymbol.canonical_symbol.in_(wanted)).all()
        existing_symbols = {row.canonical_symbol for row in existing}
        if any(symbol not in existing_symbols for symbol in wanted):
            return True
    else:
        existing = query.all()
        if not existing:
            return True

    cutoff = datetime.utcnow() - max_age
    return any(not row.last_refreshed_at or row.last_refreshed_at < cutoff for row in existing)


def sync_broker_symbols_for_account(
    db: Session,
    account: models.BrokerAccount,
    *,
    preferred_symbols: Optional[Iterable[str]] = None,
) -> SymbolSyncResult:
    if not account.metaapi_account_id:
        return SymbolSyncResult(error="Account is not connected through MetaApi")

    preferred = {s.upper() for s in preferred_symbols or []}
    now = datetime.utcnow()

    try:
        raw_symbols = metaapi.get_symbols(account.metaapi_account_id)
    except metaapi.MetaApiError as exc:
        logger.info("Could not sync symbols for account %s: %s", account.id, exc)
        return SymbolSyncResult(error=str(exc))

    result = SymbolSyncResult()
    for raw in raw_symbols:
        broker_symbol = _broker_symbol_name(raw).strip()
        if not broker_symbol:
            result.skipped += 1
            continue

        canonical = canonical_symbol_for_broker_symbol(broker_symbol)
        if not canonical or (preferred and canonical not in preferred):
            result.skipped += 1
            continue

        spec: dict = {}
        try:
            spec = metaapi.get_symbol_specification(account.metaapi_account_id, broker_symbol)
        except metaapi.MetaApiError as exc:
            logger.debug("Symbol specification unavailable for %s: %s", broker_symbol, exc)

        row = (
            db.query(models.BrokerSymbol)
            .filter(
                models.BrokerSymbol.broker_account_id == account.id,
                models.BrokerSymbol.broker_symbol == broker_symbol,
            )
            .first()
        )
        if row is None:
            row = models.BrokerSymbol(
                broker_account_id=account.id,
                broker_symbol=broker_symbol,
            )
            db.add(row)

        row.canonical_symbol = canonical
        row.display_name = broker_symbol
        row.category = SYMBOL_CATEGORIES.get(canonical)
        row.digits = _spec_value(spec, "digits")
        row.point = _spec_value(spec, "point")
        row.tick_size = _spec_value(spec, "tickSize", "tick_size")
        row.tick_value = _spec_value(spec, "lossTickValue", "loss_tick_value")
        row.contract_size = _spec_value(spec, "contractSize", "contract_size")
        row.volume_min = _spec_value(spec, "minVolume", "volumeMin", "volume_min")
        row.volume_max = _spec_value(spec, "maxVolume", "volumeMax", "volume_max")
        row.volume_step = _spec_value(spec, "volumeStep", "lotStep", "volume_step")
        row.trade_allowed = _spec_value(spec, "tradeAllowed", "trade_allowed") is not False
        row.last_refreshed_at = now
        result.synced += 1

    return result


def default_symbols_for_account(db: Session, account_id: int, limit: int = 6) -> list[str]:
    rows = (
        db.query(models.BrokerSymbol.canonical_symbol)
        .filter(
            models.BrokerSymbol.broker_account_id == account_id,
            models.BrokerSymbol.trade_allowed == True,  # noqa: E712
        )
        .distinct()
        .all()
    )
    available = {row[0] for row in rows if row[0]}
    ordered = [symbol for symbol in DEFAULT_SCAN_SYMBOL_PRIORITY if symbol in available]
    if len(ordered) < limit:
        ordered.extend(sorted(available - set(ordered)))
    return ordered[:limit]
