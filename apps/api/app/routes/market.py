import asyncio
import json
from datetime import datetime, UTC
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.database import get_db
from app.services.chart_analysis import engine as chart_analysis_engine
from app.services.chart_analysis.models import ChartAnalysisResponse
from app.services import news
from app.services.execution import ExecutionError, resolve_broker_symbol
from app.services.mt5_bridge.store import (
    get_account_snapshot,
    get_candles as get_bridge_candles,
    get_quote as get_bridge_quote,
    list_candle_symbols,
    list_quote_symbols,
)

from app.services.ai_runtime import AIProviderError, AIProviderNotConfigured, ai_health_details, analyze_json

router = APIRouter()

_auth = __import__('app.auth', fromlist=['get_current_user']).get_current_user

TIMEFRAME_MAP = {
    "M1": "1m",
    "M5": "5m",
    "M15": "15m",
    "M30": "30m",
    "H1": "1h",
    "H4": "4h",
    "D1": "1d",
    "W1": "1w",
    "MN1": "1mn",
}


def _get_user_account(account_id: int, user_id: int, db: Session) -> models.BrokerAccount:
    account = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.id == account_id,
        models.BrokerAccount.user_id == user_id,
        models.BrokerAccount.is_active == True,
    ).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker account not found")
    return account

def _is_direct_bridge_account(account: models.BrokerAccount) -> bool:
    return account.broker == "direct-mt5" or account.connection_state == "direct_connected"


def _require_direct_bridge_account(account: models.BrokerAccount) -> None:
    if not _is_direct_bridge_account(account):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="MetaApi broker adapter is disabled. Use a direct MT5 bridge account.",
        )


def _quote_age_seconds(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        quote_time = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (datetime.now(UTC) - quote_time).total_seconds()
    except Exception:
        return 0.0


def _latest_candle_quote(account_id: int, broker_symbol: str) -> dict | None:
    latest: dict | None = None
    latest_ts: datetime | None = None
    for timeframe in ("M1", "M5", "M15", "M30", "H1"):
        candles = get_bridge_candles(account_id, broker_symbol, timeframe, 1)
        if not candles:
            continue
        candle = candles[-1]
        close = float(candle.get("close") or 0.0)
        if close <= 0:
            continue
        raw_time = candle.get("time") or candle.get("brokerTime") or candle.get("timestamp")
        parsed_time = None
        if raw_time:
            try:
                parsed_time = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
            except Exception:
                parsed_time = None
        if latest is None or (parsed_time and (latest_ts is None or parsed_time > latest_ts)):
            latest_ts = parsed_time
            latest = {
                "symbol": broker_symbol.upper(),
                "bid": close,
                "ask": close,
                "spread": 0.0,
                "time": raw_time or "",
                "source": "latest_mt5_candle_close",
            }
    return latest

def _resolve_analysis_symbol(
    db: Session,
    account: models.BrokerAccount,
    requested_symbol: str,
) -> tuple[str, str]:
    lookup = requested_symbol.strip().upper()
    if not lookup:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="symbol is required")

    broker_symbols = db.query(models.BrokerSymbol).filter(
        models.BrokerSymbol.broker_account_id == account.id,
    ).all()
    for row in broker_symbols:
        if (row.broker_symbol or "").strip().upper() == lookup:
            return (row.canonical_symbol or row.broker_symbol).upper(), row.broker_symbol
    for row in broker_symbols:
        if (row.canonical_symbol or "").strip().upper() == lookup:
            return row.canonical_symbol.upper(), row.broker_symbol

    try:
        resolved = resolve_broker_symbol(db, lookup, account)
    except ExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    row = next((item for item in broker_symbols if (item.broker_symbol or "").strip().upper() == resolved.upper()), None)
    canonical = (row.canonical_symbol if row and row.canonical_symbol else lookup).upper()
    return canonical, resolved


def _canonical_timeframe_label(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="timeframe is required")

    reverse_map = {normalized.lower(): label for label, normalized in TIMEFRAME_MAP.items()}
    lowered = text.lower()
    if lowered in reverse_map:
        return reverse_map[lowered]

    uppered = text.upper()
    if uppered in TIMEFRAME_MAP:
        return uppered

    return uppered


def _analysis_event_payload(analysis: ChartAnalysisResponse, *, cached: bool) -> dict:
    payload = analysis.model_dump(mode="json")
    payload["cached"] = cached
    payload["analysis_type"] = "deterministic_chart_analysis"
    return payload


@router.get("/accounts/{account_id}/status")
async def get_market_status(
    account_id: int,
    current_user: dict = Depends(_auth),
    db: Session = Depends(get_db)
):
    account = _get_user_account(account_id, current_user["user_id"], db)
    _require_direct_bridge_account(account)
    snapshot = get_account_snapshot(account.id) or {}
    return {
        "provider": "direct-mt5",
        "platform": "mt5",
        "broker_account_id": account.id,
        "masked_login": f"{account.account_id[:3]}***" if account.account_id else "",
        "broker": account.broker,
        "server": account.server,
        "account_type": account.account_type,
        "connection_state": account.connection_state or "direct_connected",
        "synchronization_state": "connected" if snapshot else "waiting_for_ea",
        "is_live_data": bool(snapshot),
    }

@router.get("/accounts/{account_id}/symbols")
async def get_market_symbols(
    account_id: int,
    current_user: dict = Depends(_auth),
    db: Session = Depends(get_db)
):
    account = _get_user_account(account_id, current_user["user_id"], db)
    _require_direct_bridge_account(account)
    symbols = db.query(models.BrokerSymbol).filter(
        models.BrokerSymbol.broker_account_id == account.id,
        models.BrokerSymbol.trade_allowed == True
    ).all()
    snapshot = get_account_snapshot(account.id)
    snapshot_symbols = sorted({
        str(item.get("symbol") or item.get("broker_symbol") or "").upper()
        for item in (snapshot or {}).get("symbols", [])
        if isinstance(item, dict) and (item.get("symbol") or item.get("broker_symbol"))
    })
    bridge_symbols = sorted(set(snapshot_symbols) | set(list_quote_symbols(account.id)) | set(list_candle_symbols(account.id)))
    rows = [
        {
            "canonical_symbol": s.canonical_symbol,
            "broker_symbol": s.broker_symbol,
            "display_name": s.display_name,
            "category": s.category,
        } for s in symbols
    ]
    existing = {str(row["broker_symbol"]).upper() for row in rows}
    rows.extend(
        {"canonical_symbol": symbol, "broker_symbol": symbol, "display_name": symbol, "category": "mt5"}
        for symbol in bridge_symbols
        if symbol.upper() not in existing
    )
    return {
        "provider": "direct-mt5",
        "platform": "mt5",
        "broker_account_id": account.id,
        "symbols": rows,
    }

@router.post("/accounts/{account_id}/sync-symbols")
async def sync_market_symbols(
    account_id: int,
    current_user: dict = Depends(_auth),
    db: Session = Depends(get_db)
):
    account = _get_user_account(account_id, current_user["user_id"], db)
    _require_direct_bridge_account(account)
    snapshot = get_account_snapshot(account.id) or {}
    symbols = snapshot.get("symbols") if isinstance(snapshot.get("symbols"), list) else []
    return {"status": "success", "provider": "direct-mt5", "synced": len(symbols)}

@router.get("/accounts/{account_id}/symbols/{broker_symbol}/specification")
async def get_symbol_specification(
    account_id: int,
    broker_symbol: str,
    current_user: dict = Depends(_auth),
    db: Session = Depends(get_db)
):
    account = _get_user_account(account_id, current_user["user_id"], db)
    _require_direct_bridge_account(account)
    bs = db.query(models.BrokerSymbol).filter(
        models.BrokerSymbol.broker_account_id == account.id,
        models.BrokerSymbol.broker_symbol == broker_symbol
    ).first()
    return {
        "provider": "direct-mt5",
        "platform": "mt5",
        "broker_account_id": account.id,
        "broker_symbol": bs.broker_symbol if bs else broker_symbol.upper(),
        "canonical_symbol": bs.canonical_symbol if bs else broker_symbol.upper(),
        "digits": bs.digits if bs else None,
        "point": bs.point if bs else None,
        "tick_size": bs.tick_size if bs else None,
        "tick_value": bs.tick_value if bs else None,
        "contract_size": bs.contract_size if bs else None,
        "volume_min": bs.volume_min if bs else None,
        "volume_max": bs.volume_max if bs else None,
        "volume_step": bs.volume_step if bs else None,
        "trade_allowed": bs.trade_allowed if bs else True,
    }

@router.get("/accounts/{account_id}/symbols/{broker_symbol}/quote")
async def get_symbol_quote(
    account_id: int,
    broker_symbol: str,
    current_user: dict = Depends(_auth),
    db: Session = Depends(get_db)
):
    account = _get_user_account(account_id, current_user["user_id"], db)
    _require_direct_bridge_account(account)
    quote = get_bridge_quote(account.id, broker_symbol)
    fallback = False
    if not quote:
        quote = _latest_candle_quote(account.id, broker_symbol)
        fallback = True
    if not quote:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No direct MT5 quote or candle data has been received for this symbol")
    bid = float(quote.get("bid") or quote.get("brokerBid") or 0.0)
    ask = float(quote.get("ask") or quote.get("brokerAsk") or 0.0)
    spread = float(quote.get("spread") or (ask - bid if ask and bid else 0.0))
    quote_time_str = quote.get("time") or quote.get("brokerTime") or quote.get("timestamp") or quote.get("received_at") or ""
    age = _quote_age_seconds(quote_time_str)
    return {
        "provider": "direct-mt5",
        "platform": "mt5",
        "broker_account_id": account.id,
        "exact_broker_symbol": broker_symbol,
        "bid": bid,
        "ask": ask,
        "spread": spread,
        "quote_timestamp": quote_time_str,
        "quote_age": age,
        "is_live_data": (not fallback) and age <= settings.QUOTE_STALE_AFTER_SECONDS,
        "fallback_quote": fallback,
        "connection_state": account.connection_state,
    }

@router.get("/accounts/{account_id}/symbols/{broker_symbol}/candles")
async def get_symbol_candles(
    account_id: int,
    broker_symbol: str,
    timeframe: str = "H1",
    count: int = 300,
    current_user: dict = Depends(_auth),
    db: Session = Depends(get_db)
):
    account = _get_user_account(account_id, current_user["user_id"], db)
    _require_direct_bridge_account(account)
    candles = get_bridge_candles(account.id, broker_symbol, timeframe, count)
    if not candles:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No direct MT5 candles have been received for this symbol and timeframe")
    return {
        "provider": "direct-mt5",
        "platform": "mt5",
        "broker_account_id": account.id,
        "exact_broker_symbol": broker_symbol,
        "timeframe": timeframe,
        "candles": candles,
    }

@router.get("/accounts/{account_id}/symbols/{broker_symbol}/analysis", response_model=ChartAnalysisResponse)
async def get_symbol_analysis(
    account_id: int,
    broker_symbol: str,
    timeframe: str = "H1",
    count: int = Query(300, ge=50, le=1000),
    include: str = Query("all", description="Comma-separated optional sections such as support_resistance, patterns, ai"),
    force_refresh: bool = Query(False, description="Recompute even if a cached analysis is available"),
    current_user: dict = Depends(_auth),
    db: Session = Depends(get_db),
):
    account = _get_user_account(account_id, current_user["user_id"], db)
    _require_direct_bridge_account(account)
    analysis_timeframe = _canonical_timeframe_label(timeframe)

    symbol = broker_symbol.strip().upper()
    exact_broker_symbol = symbol
    candles = get_bridge_candles(account.id, exact_broker_symbol, analysis_timeframe, count)

    if not candles:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No live MT5 candle data is available")

    last_candle = candles[-1]
    last_candle_time = chart_analysis_engine.parse_chart_time(
        last_candle.get("time") or last_candle.get("brokerTime") or last_candle.get("broker_time")
    )
    if last_candle_time is None:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="MT5 candles did not include a valid timestamp")

    include_set = chart_analysis_engine.parse_include(include)
    if not force_refresh:
        cached = chart_analysis_engine.get_cached_analysis(
            account_id=account.id,
            broker_symbol=exact_broker_symbol,
            timeframe=analysis_timeframe,
            latest_candle_time=last_candle_time,
            count=count,
            include=include_set,
        )
        if cached is not None:
            return cached

    analysis = chart_analysis_engine.analyze_chart(
        symbol=symbol,
        broker_symbol=exact_broker_symbol,
        timeframe=analysis_timeframe,
        candles=candles,
        include=include,
    )
    chart_analysis_engine.cache_analysis(
        account_id=account.id,
        broker_symbol=exact_broker_symbol,
        timeframe=analysis_timeframe,
        latest_candle_time=last_candle_time,
        count=count,
        include=include_set,
        analysis=analysis,
    )
    chart_analysis_engine.publish_analysis_event(
        account.id,
        _analysis_event_payload(analysis, cached=False),
    )
    return analysis

@router.get("/accounts/{account_id}/positions")
async def get_account_positions(
    account_id: int,
    current_user: dict = Depends(_auth),
    db: Session = Depends(get_db)
):
    account = _get_user_account(account_id, current_user["user_id"], db)
    _require_direct_bridge_account(account)
    snapshot = get_account_snapshot(account.id) or {}
    positions = snapshot.get("positions") if isinstance(snapshot.get("positions"), list) else []
    return {"provider": "direct-mt5", "platform": "mt5", "broker_account_id": account.id, "positions": positions}

@router.get("/accounts/{account_id}/orders")
async def get_account_orders(
    account_id: int,
    current_user: dict = Depends(_auth),
    db: Session = Depends(get_db)
):
    account = _get_user_account(account_id, current_user["user_id"], db)
    _require_direct_bridge_account(account)
    snapshot = get_account_snapshot(account.id) or {}
    orders = snapshot.get("orders") if isinstance(snapshot.get("orders"), list) else []
    return {"provider": "direct-mt5", "platform": "mt5", "broker_account_id": account.id, "orders": orders}

@router.get("/news")
async def get_news(symbol: str | None = None, current_user: dict = Depends(_auth)):
    try:
        events = news.upcoming_events(symbol)
    except news.NewsError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return {"symbol": symbol.upper() if symbol else None, "events": events}


@router.post("/news/analyze")
async def analyze_news_impact(
    payload: dict,
    current_user: dict = Depends(_auth),
    db: Session = Depends(get_db)
):
    symbol = str(payload.get("symbol", "")).upper().strip()
    if not symbol:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="symbol is required")
    if not ai_health_details()["is_available"]:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI service not configured")

    cached = news.get_cached_impact(symbol)
    if cached:
        return cached

    try:
        events = news.upcoming_events(symbol)
    except news.NewsError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    if not events:
        result = {
            "symbol": symbol,
            "summary": "No economic events scheduled in the next 7 days for this market.",
            "events": [],
        }
        news.set_cached_impact(symbol, result)
        return result

    event_lines = "\n".join(
        f"- {e['date']} | {e['currency']} | {e['impact']} | {e['title']}"
        for e in events[:20]
    )
    prompt = (
        "You are a macro analyst for retail traders. Respond with ONLY a JSON object: "
        '{"summary": <3-5 sentence plain-language outlook for the symbol>, '
        '"key_events": [{"title": str, "when": str, "expectation": <one sentence>}]}\n\n'
        f"Symbol: {symbol}\nEconomic events:\n{event_lines}"
    )
    try:
        data = analyze_json(prompt, temperature=0.3)
    except AIProviderNotConfigured:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI service not configured")
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"News analysis failed: {exc}")

    result = {
        "symbol": symbol,
        "summary": str(data.get("summary", "")),
        "key_events": data.get("key_events") or [],
        "events": events[:20],
    }
    news.set_cached_impact(symbol, result)
    return result


@router.websocket("/accounts/{account_id}/quotes/ws")
async def ws_quotes(
    websocket: WebSocket,
    account_id: int,
    token: str,
    symbols: Optional[str] = None,
):
    await websocket.accept()
    
    # 1. Authenticate token
    from app.auth import verify_token
    try:
        payload = verify_token(token)
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2. Check account ownership
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        account = db.query(models.BrokerAccount).filter(
            models.BrokerAccount.id == account_id,
            models.BrokerAccount.user_id == user_id,
            models.BrokerAccount.is_active == True,
        ).first()
        if not account:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    finally:
        db.close()

    # 3. Subscribe to PubSub channel
    import redis
    import asyncio
    
    r = redis.Redis.from_url(settings.REDIS_URL)
    pubsub = r.pubsub()
    pubsub.subscribe(f"channel:quotes:{account_id}")

    sub_symbols = [s.strip().upper() for s in symbols.split(",")] if symbols else []

    try:
        last_heartbeat = asyncio.get_event_loop().time()
        while True:
            message = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
            if message:
                data_str = message["data"].decode("utf-8")
                try:
                    quote_data = json.loads(data_str)
                    quote_symbol = str(quote_data.get("symbol", "")).upper()
                    
                    # Quote age & stale-data warning check
                    quote_time_str = quote_data.get("time") or quote_data.get("brokerTime")
                    stale = False
                    age = None
                    if quote_time_str:
                        try:
                            qt = datetime.fromisoformat(quote_time_str.replace("Z", "+00:00"))
                            age = (datetime.now(UTC) - qt).total_seconds()
                            stale = age > settings.QUOTE_STALE_AFTER_SECONDS
                        except Exception:
                            pass
                    
                    quote_data["quote_age_seconds"] = age
                    quote_data["stale_data_warning"] = stale

                    if not sub_symbols or quote_symbol in sub_symbols:
                        await websocket.send_json({
                            "type": "quote",
                            "data": quote_data
                        })
                except Exception:
                    pass

            # Heartbeat (every 10 seconds)
            now_time = asyncio.get_event_loop().time()
            if now_time - last_heartbeat > 10.0:
                await websocket.send_json({"type": "heartbeat", "timestamp": datetime.utcnow().isoformat()})
                last_heartbeat = now_time

            # Small sleep to yield execution loop
            await asyncio.sleep(0.01)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error(f"Quotes WebSocket error: {exc}", exc_info=True)
    finally:
        try:
            pubsub.unsubscribe()
            pubsub.close()
        except Exception:
            pass


@router.websocket("/accounts/{account_id}/analysis/ws")
async def ws_analysis(
    websocket: WebSocket,
    account_id: int,
    token: str,
    symbols: Optional[str] = None,
):
    await websocket.accept()

    from app.auth import verify_token
    try:
        payload = verify_token(token)
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    from app.database import SessionLocal
    db = SessionLocal()
    try:
        account = db.query(models.BrokerAccount).filter(
            models.BrokerAccount.id == account_id,
            models.BrokerAccount.user_id == user_id,
            models.BrokerAccount.is_active == True,
        ).first()
        if not account:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    finally:
        db.close()

    import redis

    r = redis.Redis.from_url(settings.REDIS_URL)
    pubsub = r.pubsub()
    pubsub.subscribe(
        f"channel:quotes:{account_id}",
        f"channel:candles:{account_id}",
        f"channel:analysis:{account_id}",
        f"channel:signals:{account_id}",
    )

    sub_symbols = [s.strip().upper() for s in symbols.split(",")] if symbols else []

    try:
        last_heartbeat = asyncio.get_event_loop().time()
        while True:
            message = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
            if message:
                try:
                    channel = message.get("channel")
                    if isinstance(channel, bytes):
                        channel = channel.decode("utf-8")
                    data_str = message["data"].decode("utf-8")
                    payload = json.loads(data_str)
                    event_type = "analysis"
                    if isinstance(channel, str):
                        if channel.startswith("channel:quotes:"):
                            event_type = "quote"
                        elif channel.startswith("channel:candles:"):
                            event_type = "candle"
                        elif channel.startswith("channel:signals:"):
                            event_type = "signal"

                    payload_symbol = str(payload.get("symbol") or payload.get("broker_symbol") or payload.get("exact_broker_symbol") or "").upper()
                    if sub_symbols and payload_symbol and payload_symbol not in sub_symbols:
                        continue

                    await websocket.send_json({
                        "type": event_type,
                        "data": payload,
                    })
                except Exception:
                    pass

            now_time = asyncio.get_event_loop().time()
            if now_time - last_heartbeat > 10.0:
                await websocket.send_json({"type": "heartbeat", "timestamp": datetime.utcnow().isoformat()})
                last_heartbeat = now_time

            await asyncio.sleep(0.01)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error(f"Analysis WebSocket error: {exc}", exc_info=True)
    finally:
        try:
            pubsub.unsubscribe()
            pubsub.close()
        except Exception:
            pass
