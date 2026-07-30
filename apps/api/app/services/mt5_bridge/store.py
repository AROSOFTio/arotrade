from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import redis
from fastapi import Header, HTTPException, status
from sqlalchemy.orm import Session

from app import models
from app.config import settings


def redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def authenticate_bridge_key(db: Session, api_key: str | None) -> models.APIKey:
    key = (api_key or "").strip()
    if not key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bridge API key")
    record = db.query(models.APIKey).filter(models.APIKey.key == key, models.APIKey.is_active == True).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bridge API key")
    record.last_used = datetime.utcnow()
    return record


def require_bridge_account(db: Session, api_key: str | None, account_id: int) -> models.BrokerAccount:
    key_record = authenticate_bridge_key(db, api_key)
    account = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.id == account_id,
        models.BrokerAccount.user_id == key_record.user_id,
        models.BrokerAccount.is_active == True,
    ).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bridge account not found")
    return account


def normalise_candle(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "time": raw.get("time") or raw.get("brokerTime") or raw.get("timestamp"),
        "open": float(raw.get("open") or raw.get("open_price") or 0),
        "high": float(raw.get("high") or raw.get("high_price") or 0),
        "low": float(raw.get("low") or raw.get("low_price") or 0),
        "close": float(raw.get("close") or raw.get("close_price") or 0),
        "volume": float(raw.get("volume") or raw.get("tickVolume") or 0),
    }


def store_candles(account_id: int, symbol: str, timeframe: str, candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = [normalise_candle(candle) for candle in candles if isinstance(candle, dict)]
    cleaned = [candle for candle in cleaned if candle["open"] and candle["high"] and candle["low"] and candle["close"]]
    cleaned = cleaned[-1000:]
    key = candles_key(account_id, symbol, timeframe)
    client = redis_client()
    client.set(key, json.dumps(cleaned), ex=60 * 60 * 24 * 7)
    if cleaned:
        client.publish(f"channel:candles:{account_id}", json.dumps({
            "provider": "direct-mt5",
            "account_id": account_id,
            "symbol": symbol.upper(),
            "timeframe": timeframe.upper(),
            "latest": cleaned[-1],
            "count": len(cleaned),
        }))
    return cleaned


def store_quote(account_id: int, payload: dict[str, Any]) -> None:
    symbol = str(payload.get("symbol") or "").upper()
    if not symbol:
        return
    data = {**payload, "provider": "direct-mt5", "account_id": account_id}
    client = redis_client()
    client.set(f"mt5:quote:{account_id}:{symbol}", json.dumps(data), ex=300)
    client.publish(f"channel:quotes:{account_id}", json.dumps(data))


def candles_key(account_id: int, symbol: str, timeframe: str) -> str:
    return f"mt5:candles:{account_id}:{symbol.upper()}:{timeframe.upper()}"


def get_candles(account_id: int, symbol: str, timeframe: str, count: int = 240) -> list[dict[str, Any]]:
    raw = redis_client().get(candles_key(account_id, symbol, timeframe))
    if not raw:
        return []
    try:
        candles = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(candles, list):
        return []
    return candles[-count:]