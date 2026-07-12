from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.config import settings
from app.services import metaapi_gateway as metaapi
from app.services.gemini import (
    GeminiError,
    GeminiNotConfigured,
    answer_analysis_question,
    run_chart_analysis,
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

ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _persist_analysis(db: Session, user_id: int, symbol: str, timeframe: str, prompt, result: dict) -> models.AIAnalysis:
    analysis = models.AIAnalysis(
        user_id=user_id,
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
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


def _run_or_raise(**kwargs) -> dict:
    try:
        return run_chart_analysis(**kwargs)
    except GeminiNotConfigured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured"
        )
    except GeminiError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI analysis failed: {exc}"
        )


@router.post("/analyze", response_model=schemas.AIAnalysisResponse)
async def analyze_chart(
    request: schemas.AIAnalysisRequest,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Analyze a market using Gemini AI, anchored to live candles when the symbol has a feed."""
    account = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.id == request.broker_account_id,
        models.BrokerAccount.user_id == current_user["user_id"],
        models.BrokerAccount.is_active == True,
    ).first()
    if not account or not account.metaapi_account_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active broker account connected to MetaApi not found"
        )

    result = _run_or_raise(
        symbol=request.symbol,
        timeframe=request.timeframe,
        prompt=request.prompt,
        price_context=_live_context(account.metaapi_account_id, request.symbol, request.timeframe),
    )
    return _persist_analysis(db, current_user["user_id"], request.symbol, request.timeframe, request.prompt, result)


@router.post("/analyze-image", response_model=schemas.AIAnalysisResponse)
async def analyze_image_upload(
    file: UploadFile = File(...),
    broker_account_id: int = Form(...),
    symbol: str = Form(...),
    timeframe: str = Form(...),
    prompt: str = Form(default=""),
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Analyze an uploaded chart screenshot with Gemini vision."""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Upload a PNG, JPEG or WebP chart screenshot"
        )

    image_bytes = await file.read()
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Chart image must be 8 MB or smaller"
        )
    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty"
        )

    account = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.id == broker_account_id,
        models.BrokerAccount.user_id == current_user["user_id"],
        models.BrokerAccount.is_active == True,
    ).first()
    if not account or not account.metaapi_account_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active broker account connected to MetaApi not found"
        )

    result = _run_or_raise(
        symbol=symbol,
        timeframe=timeframe,
        prompt=prompt or None,
        image_bytes=image_bytes,
        image_mime=file.content_type,
        price_context=_live_context(account.metaapi_account_id, symbol, timeframe),
    )
    return _persist_analysis(db, current_user["user_id"], symbol, timeframe, prompt or None, result)


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
        models.BrokerAccount.connection_state == "deployed",
    ).first()
    if not account or not account.metaapi_account_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No deployed and active broker account found to scan for Signal of the Day"
        )

    # Build a multi-market context and let the model pick one setup
    sections = []
    for candidate in SOTD_CANDIDATES:
        context = _live_context(account.metaapi_account_id, candidate, "H4")
        if context:
            # Keep each market compact so the combined prompt stays small
            lines = context.splitlines()
            sections.append(f"### {candidate} (H4)\n" + "\n".join([lines[0]] + lines[-60:]))
    if not sections:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Market data feed unavailable")

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
        f"Risk warning: {analysis.risk_warning or '-'}"
    )

    try:
        answer = answer_analysis_question(summary, history, question)
    except GeminiNotConfigured:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI service not configured")
    except GeminiError as exc:
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
