import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.services import marketdata, news
from app.services.gemini import GeminiError, GeminiNotConfigured

import google.generativeai as genai

router = APIRouter()

_auth = __import__('app.auth', fromlist=['get_current_user']).get_current_user


@router.get("/symbols")
async def list_symbols():
    return {"symbols": marketdata.supported_symbols(), "timeframes": list(marketdata.GRANULARITY.keys())}


@router.get("/candles")
async def get_candles(symbol: str, timeframe: str = "H1", count: int = 200, current_user: dict = Depends(_auth)):
    try:
        candles = marketdata.get_candles(symbol, timeframe, count)
    except marketdata.MarketDataError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {"symbol": symbol.upper(), "timeframe": timeframe.upper(), "candles": candles}


@router.get("/price")
async def get_price(symbol: str, current_user: dict = Depends(_auth)):
    try:
        return marketdata.get_price(symbol)
    except marketdata.MarketDataError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/news")
async def get_news(symbol: str | None = None, current_user: dict = Depends(_auth)):
    try:
        events = news.upcoming_events(symbol)
    except news.NewsError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return {"symbol": symbol.upper() if symbol else None, "events": events}


@router.post("/news/analyze")
async def analyze_news_impact(payload: dict, current_user: dict = Depends(_auth), db: Session = Depends(get_db)):
    """News IQ: Gemini reads the upcoming calendar for a symbol and explains expected impact."""
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
            "summary": "No high or medium impact economic events are scheduled in the next few days for this market."
                       + (" Synthetic indices are not driven by macro news." if not news.relevant_currencies(symbol) else ""),
            "events": [],
        }
        news.set_cached_impact(symbol, result)
        return result

    event_lines = "\n".join(
        f"- {e['date']} | {e['currency']} | {e['impact']} | {e['title']} (forecast {e['forecast'] or '-'}, previous {e['previous'] or '-'})"
        for e in events[:20]
    )
    prompt = (
        "You are a macro analyst for retail traders. Respond with ONLY a JSON object: "
        '{"summary": <3-5 sentence plain-language impact outlook for the symbol>, '
        '"key_events": [{"title": str, "when": str, "expectation": <one sentence>}]}\n\n'
        f"Symbol: {symbol}\nUpcoming economic events:\n{event_lines}"
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
