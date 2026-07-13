import json
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.database import get_db
from app.services import metaapi_gateway as metaapi, news

import google.generativeai as genai

router = APIRouter()

_auth = __import__('app.auth', fromlist=['get_current_user']).get_current_user


def _get_user_account(account_id: int, user_id: int, db: Session) -> models.BrokerAccount:
    account = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.id == account_id,
        models.BrokerAccount.user_id == user_id,
        models.BrokerAccount.is_active == True,
    ).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker account not found")
    return account


@router.get("/accounts/{account_id}/status")
async def get_market_status(
    account_id: int,
    current_user: dict = Depends(_auth),
    db: Session = Depends(get_db)
):
    account = _get_user_account(account_id, current_user["user_id"], db)
    try:
        remote = metaapi.get_account(account.metaapi_account_id)
        state = (remote.get("state") or "").lower()
        connection = (remote.get("connectionStatus") or "").lower()
        
        # update local connection state if changed
        state_str = "deployed" if state == "deployed" else state
        if account.connection_state != state_str:
            account.connection_state = state_str
            db.commit()
    except Exception:
        state = account.connection_state or "unknown"
        connection = "disconnected"

    return {
        "provider": "metaapi",
        "platform": account.platform or "mt5",
        "broker_account_id": account.id,
        "masked_login": f"{account.account_id[:3]}***" if account.account_id else "",
        "broker": account.broker,
        "server": account.server,
        "account_type": account.account_type,
        "connection_state": state,
        "synchronization_state": connection,
        "is_live_data": state == "deployed" and connection == "connected",
    }


@router.get("/accounts/{account_id}/symbols")
async def get_market_symbols(
    account_id: int,
    current_user: dict = Depends(_auth),
    db: Session = Depends(get_db)
):
    account = _get_user_account(account_id, current_user["user_id"], db)
    symbols = db.query(models.BrokerSymbol).filter(
        models.BrokerSymbol.broker_account_id == account.id,
        models.BrokerSymbol.trade_allowed == True
    ).all()

    return {
        "provider": "metaapi",
        "platform": account.platform or "mt5",
        "broker_account_id": account.id,
        "symbols": [
            {
                "canonical_symbol": s.canonical_symbol,
                "broker_symbol": s.broker_symbol,
                "display_name": s.display_name,
                "category": s.category,
            } for s in symbols
        ]
    }


@router.post("/accounts/{account_id}/sync-symbols")
async def sync_market_symbols(
    account_id: int,
    current_user: dict = Depends(_auth),
    db: Session = Depends(get_db)
):
    account = _get_user_account(account_id, current_user["user_id"], db)
    if not account.metaapi_account_id:
        raise HTTPException(status_code=400, detail="Account not connected to MetaApi")

    from app.services.broker_symbol_sync import sync_broker_symbols_for_account
    result = sync_broker_symbols_for_account(db, account)
    db.commit()
    return {"status": "success", "synced": result.synced}


@router.get("/accounts/{account_id}/symbols/{broker_symbol}/specification")
async def get_symbol_specification(
    account_id: int,
    broker_symbol: str,
    current_user: dict = Depends(_auth),
    db: Session = Depends(get_db)
):
    account = _get_user_account(account_id, current_user["user_id"], db)
    bs = db.query(models.BrokerSymbol).filter(
        models.BrokerSymbol.broker_account_id == account.id,
        models.BrokerSymbol.broker_symbol == broker_symbol
    ).first()
    if not bs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Symbol {broker_symbol} not found")

    return {
        "provider": "metaapi",
        "platform": account.platform or "mt5",
        "broker_account_id": account.id,
        "broker_symbol": bs.broker_symbol,
        "canonical_symbol": bs.canonical_symbol,
        "digits": bs.digits,
        "point": bs.point,
        "tick_size": bs.tick_size,
        "tick_value": bs.tick_value,
        "contract_size": bs.contract_size,
        "volume_min": bs.volume_min,
        "volume_max": bs.volume_max,
        "volume_step": bs.volume_step,
        "trade_allowed": bs.trade_allowed,
    }


@router.get("/accounts/{account_id}/symbols/{broker_symbol}/quote")
async def get_symbol_quote(
    account_id: int,
    broker_symbol: str,
    current_user: dict = Depends(_auth),
    db: Session = Depends(get_db)
):
    account = _get_user_account(account_id, current_user["user_id"], db)
    try:
        quote = metaapi.get_symbol_price(account.metaapi_account_id, broker_symbol, require_fresh=False)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    bid = float(quote.get("bid") or quote.get("brokerBid") or 0.0)
    ask = float(quote.get("ask") or quote.get("brokerAsk") or 0.0)
    spread = float(quote.get("spread") or (ask - bid if ask and bid else 0.0))

    quote_time_str = quote.get("time") or quote.get("brokerTime") or ""
    age = 0.0
    if quote_time_str:
        try:
            quote_time = datetime.fromisoformat(quote_time_str.replace("Z", "+00:00"))
            age = (datetime.now(UTC) - quote_time).total_seconds()
        except Exception:
            pass

    is_live = age <= settings.QUOTE_STALE_AFTER_SECONDS and account.connection_state == "deployed"

    return {
        "provider": "metaapi",
        "platform": account.platform or "mt5",
        "broker_account_id": account.id,
        "exact_broker_symbol": broker_symbol,
        "bid": bid,
        "ask": ask,
        "spread": spread,
        "quote_timestamp": quote_time_str,
        "quote_age": age,
        "is_live_data": is_live,
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
    try:
        tf = metaapi.normalize_timeframe(timeframe)
        candles = metaapi.get_candles(account.metaapi_account_id, broker_symbol, tf, count)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    return {
        "provider": "metaapi",
        "platform": account.platform or "mt5",
        "broker_account_id": account.id,
        "exact_broker_symbol": broker_symbol,
        "timeframe": timeframe,
        "candles": candles,
    }


@router.get("/accounts/{account_id}/positions")
async def get_account_positions(
    account_id: int,
    current_user: dict = Depends(_auth),
    db: Session = Depends(get_db)
):
    account = _get_user_account(account_id, current_user["user_id"], db)
    try:
        positions = metaapi.get_positions(account.metaapi_account_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    return {
        "provider": "metaapi",
        "platform": account.platform or "mt5",
        "broker_account_id": account.id,
        "positions": positions,
    }


@router.get("/accounts/{account_id}/orders")
async def get_account_orders(
    account_id: int,
    current_user: dict = Depends(_auth),
    db: Session = Depends(get_db)
):
    account = _get_user_account(account_id, current_user["user_id"], db)
    try:
        orders = metaapi.get_orders(account.metaapi_account_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    return {
        "provider": "metaapi",
        "platform": account.platform or "mt5",
        "broker_account_id": account.id,
        "orders": orders,
    }


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
    if not settings.GEMINI_API_KEY:
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
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(settings.GEMINI_MODEL)
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json", "temperature": 0.3})
        data = json.loads(response.text)
    except Exception as exc:
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
