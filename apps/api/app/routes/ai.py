from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.config import settings
from app.services import metaapi_gateway as metaapi
from app.services.analysis_engine import market_snapshot
from app.services.mt5_bridge.store import get_account_snapshot, get_candles as get_bridge_candles
from app.services.ai.provider_manager import provider_manager
from app.services.ai_runtime import (
    ProviderRuntimeError,
    ProviderRuntimeNotConfigured,
    answer_analysis_question,
    run_market_analysis,
)

router = APIRouter()

SIGNAL_OF_THE_DAY_MARKER = "[signal-of-the-day]"
SOTD_CANDIDATES = ["EURUSD", "GBPUSD", "XAUUSD", "USDJPY", "BTCUSD"]


def _live_context(metaapi_account_id: str, symbol: str, timeframe: str) -> str | None:
    """Best-effort live candle context from the connected MT5 account; None on error."""
    try:
        tf = metaapi.normalize_timeframe(timeframe)
        candles = metaapi.get_candles(metaapi_account_id, symbol, tf, 200)
        return metaapi.candles_to_prompt_context(candles)
    except Exception:
        return None


def _live_market_snapshot(metaapi_account_id: str, symbol: str, timeframe: str) -> tuple[str | None, dict | None]:
    """Return shared candle text and deterministic indicators for AI interpretation."""
    try:
        tf = metaapi.normalize_timeframe(timeframe)
        candles = metaapi.get_candles(metaapi_account_id, symbol, tf, 240)
        if not candles:
            return None, None
        return metaapi.candles_to_prompt_context(candles), market_snapshot(symbol, timeframe, candles)
    except Exception:
        return None, None

def _account_market_snapshot(account: models.BrokerAccount, symbol: str, timeframe: str) -> tuple[str | None, dict | None]:
    if account.metaapi_account_id:
        return _live_market_snapshot(account.metaapi_account_id, symbol, timeframe)
    if account.broker == "direct-mt5":
        candles = get_bridge_candles(account.id, symbol, timeframe, 240)
        if not candles:
            return None, None
        lines = ["time,open,high,low,close,volume"]
        for candle in candles[-200:]:
            lines.append(
                f"{candle.get('time')},{candle.get('open')},{candle.get('high')},{candle.get('low')},{candle.get('close')},{candle.get('volume', 0)}"
            )
        return "\n".join(lines), market_snapshot(symbol, timeframe, candles)
    return None, None



def _get_quote_and_candle_metrics(db: Session, broker_account_id: int, symbol: str, timeframe: str) -> dict:
    from app.services.order_execution import resolve_broker_symbol
    quote_time = None
    quote_age_seconds = None
    stale_data_warning = False
    candle_close_time = None

    try:
        account = db.query(models.BrokerAccount).filter(models.BrokerAccount.id == broker_account_id).first()
        if account and account.metaapi_account_id:
            broker_symbol = resolve_broker_symbol(db, symbol, account)
            # Fetch quote
            quote = metaapi.get_symbol_price(account.metaapi_account_id, broker_symbol, require_fresh=False)
            quote_time_str = quote.get("time") or quote.get("brokerTime")
            if quote_time_str:
                quote_time = datetime.fromisoformat(quote_time_str.replace("Z", "+00:00")).replace(tzinfo=None)
                quote_age_seconds = (datetime.utcnow() - quote_time).total_seconds()
                stale_data_warning = quote_age_seconds > settings.QUOTE_STALE_AFTER_SECONDS
            
            # Fetch last candle close time
            tf = metaapi.normalize_timeframe(timeframe)
            candles = metaapi.get_candles(account.metaapi_account_id, broker_symbol, tf, 2)
            if candles:
                last_candle = candles[-1]
                last_candle_time_str = last_candle.get("time") or last_candle.get("brokerTime")
                if last_candle_time_str:
                    candle_close_time = datetime.fromisoformat(last_candle_time_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        pass

    return {
        "quote_time": quote_time,
        "quote_age_seconds": quote_age_seconds,
        "stale_data_warning": stale_data_warning,
        "candle_close_time": candle_close_time,
    }


def _persist_analysis(
    db: Session,
    user_id: int,
    symbol: str,
    timeframe: str,
    prompt,
    result: dict,
    broker_account_id: Optional[int] = None,
) -> models.AIAnalysis:
    metrics = {}
    if broker_account_id:
        metrics = _get_quote_and_candle_metrics(db, broker_account_id, symbol, timeframe)

    analysis = models.AIAnalysis(
        user_id=user_id,
        broker_account_id=broker_account_id,
        symbol=symbol.upper(),
        timeframe=timeframe,
        prompt=prompt,
        analysis=result.get("raw"),
        bias=result["bias"],
        signal=result["signal"],
        confidence=result["confidence"],
        entry_min=result["entry_min"],
        entry_max=result["entry_max"],
        stop_loss=result["stop_loss"],
        take_profit_1=result["take_profit_1"],
        take_profit_2=result["take_profit_2"],
        take_profit_3=result["take_profit_3"],
        risk_reward=result["risk_reward"],
        reasoning=result["reasoning"],
        invalidation=result["invalidation"],
        news_warning=result["news_warning"],
        risk_warning=result["risk_warning"],
        candle_close_time=metrics.get("candle_close_time"),
        quote_time=metrics.get("quote_time"),
        quote_age_seconds=metrics.get("quote_age_seconds"),
        stale_data_warning=metrics.get("stale_data_warning", False),
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


def _deterministic_analysis_fallback(symbol: str, timeframe: str, prompt, deterministic: dict | None, error: Exception) -> dict:
    snapshot = deterministic or {}
    latest = snapshot.get("latest_candle") if isinstance(snapshot.get("latest_candle"), dict) else {}
    structure = snapshot.get("structure") if isinstance(snapshot.get("structure"), dict) else {}

    def _safe_float_list(values) -> list[float]:
        levels: list[float] = []
        for value in values or []:
            try:
                levels.append(float(value))
            except (TypeError, ValueError):
                continue
        return levels

    support_levels = _safe_float_list(structure.get("support"))
    resistance_levels = _safe_float_list(structure.get("resistance"))
    try:
        current_price = float(latest.get("close") or 0)
    except (TypeError, ValueError):
        current_price = 0.0
    nearest_support = max([value for value in support_levels if not current_price or value < current_price], default=None)
    nearest_resistance = min([value for value in resistance_levels if not current_price or value > current_price], default=None)
    trend = str(snapshot.get("trend") or "sideways")
    reasoning = [
        "Cloud/local AI provider failed, so AroPilot used deterministic MT5 market data instead.",
        f"Trend is currently {trend}.",
    ]
    if nearest_support:
        reasoning.append(f"Nearest support to watch: {nearest_support:.5f}.")
    if nearest_resistance:
        reasoning.append(f"Nearest resistance to watch: {nearest_resistance:.5f}.")
    reasoning.append("Next action: wait for a clean candle reaction or breakout before preparing a trade.")
    raw = {
        "fallback": "deterministic",
        "provider_error": str(error)[:500],
        "prompt": prompt,
        "snapshot": snapshot,
    }
    return {
        "bias": "neutral" if trend == "sideways" else ("bullish" if trend == "bullish" else "bearish"),
        "signal": "hold",
        "confidence": 35,
        "entry_min": 0.0,
        "entry_max": 0.0,
        "stop_loss": 0.0,
        "take_profit_1": None,
        "take_profit_2": None,
        "take_profit_3": None,
        "risk_reward": 0.0,
        "reasoning": reasoning,
        "invalidation": "A valid trade requires fresh confirmation at a mapped support/resistance level.",
        "news_warning": None,
        "risk_warning": "No trade prepared. This is a deterministic fallback because configured AI providers were unavailable.",
        "raw": raw,
    }


def _run_or_raise(**kwargs) -> dict:
    try:
        return run_market_analysis(**kwargs)
    except ProviderRuntimeNotConfigured as exc:
        return _deterministic_analysis_fallback(
            kwargs.get("symbol", ""),
            kwargs.get("timeframe", ""),
            kwargs.get("prompt"),
            kwargs.get("deterministic_analysis"),
            exc,
        )
    except ProviderRuntimeError as exc:
        return _deterministic_analysis_fallback(
            kwargs.get("symbol", ""),
            kwargs.get("timeframe", ""),
            kwargs.get("prompt"),
            kwargs.get("deterministic_analysis"),
            exc,
        )


@router.get("/providers")
async def list_ai_providers(
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
):
    """Return all supported providers with graceful availability labels."""
    del current_user
    return {"providers": [status.__dict__ for status in provider_manager.all_statuses()]}


@router.post("/compare")
async def compare_ai_models(
    request: schemas.AIAnalysisRequest,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db),
):
    """Analyze one MT5 market snapshot with every provider and expose consensus/disagreement."""
    account = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.id == request.broker_account_id,
        models.BrokerAccount.user_id == current_user["user_id"],
        models.BrokerAccount.is_active == True,
    ).first()
    if not account or (not account.metaapi_account_id and account.broker != "direct-mt5"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active direct MT5 bridge account not found",
        )

    price_context, deterministic = _account_market_snapshot(account, request.symbol, request.timeframe)
    comparison = provider_manager.compare(
        symbol=request.symbol,
        timeframe=request.timeframe,
        prompt=request.prompt,
        image_bytes=None,
        image_mime=None,
        price_context=price_context,
        deterministic_analysis=deterministic,
    )
    comparison["market"] = {"symbol": request.symbol.upper(), "timeframe": request.timeframe}
    comparison["deterministic_analysis"] = deterministic
    return comparison

@router.post("/analyze", response_model=schemas.AIAnalysisResponse)
async def analyze_chart(
    request: schemas.AIAnalysisRequest,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Analyze a market from live MT5 candles through the provider framework."""
    account = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.id == request.broker_account_id,
        models.BrokerAccount.user_id == current_user["user_id"],
        models.BrokerAccount.is_active == True,
    ).first()
    if not account or (not account.metaapi_account_id and account.broker != "direct-mt5"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active direct MT5 bridge account not found"
        )

    price_context, deterministic = _account_market_snapshot(account, request.symbol, request.timeframe)
    result = _run_or_raise(
        symbol=request.symbol,
        timeframe=request.timeframe,
        prompt=request.prompt,
        price_context=price_context,
        deterministic_analysis=deterministic,
    )
    return _persist_analysis(
        db,
        current_user["user_id"],
        request.symbol,
        request.timeframe,
        request.prompt,
        result,
        request.broker_account_id,
    )


def _extract_sotd_symbol(result: dict) -> str:
    for reason in result.get("reasoning", []):
        text = str(reason)
        if text.lower().startswith("selected market:"):
            candidate = text.split(":", 1)[1].strip().upper()
            if candidate in SOTD_CANDIDATES:
                return candidate
        for candidate in SOTD_CANDIDATES:
            if candidate in text.upper():
                return candidate
    return "EURUSD"


@router.get("/signal-of-the-day", response_model=schemas.AIAnalysisResponse)
async def signal_of_the_day(
    refresh: bool = Query(False, description="Generate a fresh AI pick instead of returning today's cached setup"),
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """One AI-picked setup per day: scans the candidate list on live H4 candles
    and publishes the highest-conviction setup. Generated once per UTC day by
    whichever user asks first; everyone sees the same signal."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
    existing = db.query(models.AIAnalysis).filter(
        models.AIAnalysis.prompt == SIGNAL_OF_THE_DAY_MARKER,
        models.AIAnalysis.created_at >= today_start,
    ).order_by(models.AIAnalysis.created_at.desc()).first()
    if existing and not refresh:
        return existing

    account = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.user_id == current_user["user_id"],
        models.BrokerAccount.is_active == True,
        models.BrokerAccount.broker == "direct-mt5",
        models.BrokerAccount.connection_state == "direct_connected",
    ).first()
    if not account:
        account = db.query(models.BrokerAccount).filter(
            models.BrokerAccount.user_id == current_user["user_id"],
            models.BrokerAccount.is_active == True,
            models.BrokerAccount.connection_state == "deployed",
            models.BrokerAccount.metaapi_account_id.isnot(None),
        ).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active MT5 bridge account found to scan for Signal of the Day"
        )

    sections = []
    for candidate in SOTD_CANDIDATES:
        context, deterministic = _account_market_snapshot(account, candidate, "H4")
        if context:
            lines = context.splitlines()
            sections.append(
                f"### {candidate} (H4)\n"
                + "\n".join([lines[0]] + lines[-60:])
                + "\nDeterministic snapshot: "
                + str(deterministic or {})
            )
    if not sections:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="MT5 market data feed unavailable")
    selection_prompt = (
        "You are given live H4 candles for several markets. Pick the SINGLE best "
        "risk-defined setup right now among them and produce your analysis for that "
        "market only. Set the symbol you chose as the first reasoning entry, "
        "formatted exactly like: 'Selected market: <SYMBOL>'. If no market has a "
        "clean risk-defined setup, return signal hold with low confidence and still "
        "choose the clearest market from the supplied list."
    )
    result = _run_or_raise(symbol="MULTI", timeframe="H4", prompt=selection_prompt, price_context="\n\n".join(sections))
    chosen = _extract_sotd_symbol(result)

    analysis = models.AIAnalysis(
        user_id=current_user["user_id"],
        symbol=chosen,
        timeframe="H4",
        prompt=SIGNAL_OF_THE_DAY_MARKER,
        analysis=result.get("raw"),
        bias=result["bias"],
        signal=result["signal"],
        confidence=result["confidence"],
        entry_min=result["entry_min"],
        entry_max=result["entry_max"],
        stop_loss=result["stop_loss"],
        take_profit_1=result["take_profit_1"],
        take_profit_2=result["take_profit_2"],
        take_profit_3=result["take_profit_3"],
        risk_reward=result["risk_reward"],
        reasoning=result["reasoning"],
        invalidation=result["invalidation"],
        news_warning=result["news_warning"],
        risk_warning=result["risk_warning"],
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis



def _analysis_live_context(db: Session, analysis: models.AIAnalysis) -> str:
    if not analysis.broker_account_id:
        return "Live account context: no broker account is attached to this analysis."
    account = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.id == analysis.broker_account_id,
        models.BrokerAccount.user_id == analysis.user_id,
        models.BrokerAccount.is_active == True,
    ).first()
    if not account:
        return "Live account context: broker account is no longer active."
    parts = [
        "Live account context:",
        f"Account: {account.name or account.account_id} | provider {account.broker} | {account.account_type} | state {account.connection_state}",
        f"Balance: {account.balance or 0} {account.currency or 'USD'}",
    ]
    if account.broker == "direct-mt5" or account.connection_state == "direct_connected":
        snapshot = get_account_snapshot(account.id) or {}
        positions = snapshot.get("positions") if isinstance(snapshot.get("positions"), list) else []
        orders = snapshot.get("orders") if isinstance(snapshot.get("orders"), list) else []
        parts.append(f"EA snapshot received: {snapshot.get('received_at') or 'unavailable'}")
        parts.append(f"Open MT5 positions: {len(positions)} | pending orders: {len(orders)}")
        for position in positions[:5]:
            if isinstance(position, dict):
                parts.append(
                    "Position: "
                    + f"{position.get('symbol', 'UNKNOWN')} {position.get('type') or position.get('direction') or ''} "
                    + f"volume {position.get('volume') or position.get('lots') or '-'} "
                    + f"profit {position.get('profit') or position.get('unrealizedProfit') or position.get('floatingProfit') or 0}"
                )
    else:
        parts.append("Optional MetaApi adapter account; live snapshot is pulled through adapter-specific endpoints.")
    return "\n".join(parts)

@router.post("/analyses/{analysis_id}/chat")
async def chat_about_analysis(
    analysis_id: int,
    payload: dict,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Follow-up Q&A about one of the user's analyses (plain-language mentor mode)."""
    question = str(payload.get("question", "")).strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="question is required")
    history = payload.get("history") or []
    if not isinstance(history, list):
        history = []

    analysis = db.query(models.AIAnalysis).filter(
        models.AIAnalysis.id == analysis_id,
        models.AIAnalysis.user_id == current_user["user_id"]
    ).first()
    if not analysis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")

    summary = (
        f"{analysis.symbol} {analysis.timeframe} | bias {analysis.bias} | signal {analysis.signal} "
        f"| confidence {analysis.confidence}% | entry {analysis.entry_min}-{analysis.entry_max} "
        f"| stop loss {analysis.stop_loss} | targets {analysis.take_profit_1}/{analysis.take_profit_2}/{analysis.take_profit_3} "
        f"| reward:risk {analysis.risk_reward}\n"
        f"Reasoning: {'; '.join(analysis.reasoning or [])}\n"
        f"Invalidation: {analysis.invalidation}\n"
        f"Risk warning: {analysis.risk_warning or '-'}\n"
        f"{_analysis_live_context(db, analysis)}"
    )

    try:
        answer = answer_analysis_question(summary, history, question)
    except ProviderRuntimeNotConfigured:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI service not configured")
    except ProviderRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI chat failed: {exc}")

    return {"answer": answer}


@router.get("/analyses")
async def list_analyses(
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 50
):
    """List user's AI analyses."""
    analyses = db.query(models.AIAnalysis).filter(
        models.AIAnalysis.user_id == current_user["user_id"]
    ).order_by(models.AIAnalysis.created_at.desc()).offset(skip).limit(limit).all()

    return analyses


@router.get("/analyses/{analysis_id}")
async def get_analysis(
    analysis_id: int,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Get specific analysis."""
    analysis = db.query(models.AIAnalysis).filter(
        models.AIAnalysis.id == analysis_id,
        models.AIAnalysis.user_id == current_user["user_id"]
    ).first()

    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found"
        )

    return analysis
