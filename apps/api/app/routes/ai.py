from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.config import settings
from app.services import marketdata
from app.services.gemini import GeminiError, GeminiNotConfigured, run_chart_analysis

router = APIRouter()

SIGNAL_OF_THE_DAY_MARKER = "[signal-of-the-day]"
SOTD_CANDIDATES = ["EURUSD", "GBPUSD", "XAUUSD", "USDJPY", "BTCUSD", "V75"]


def _live_context(symbol: str, timeframe: str) -> str | None:
    """Best-effort live candle context; None when the symbol has no feed."""
    try:
        candles = marketdata.get_candles(symbol, timeframe, 200)
        return marketdata.candles_to_prompt_context(candles)
    except marketdata.MarketDataError:
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
    result = _run_or_raise(
        symbol=request.symbol,
        timeframe=request.timeframe,
        prompt=request.prompt,
        price_context=_live_context(request.symbol, request.timeframe),
    )
    return _persist_analysis(db, current_user["user_id"], request.symbol, request.timeframe, request.prompt, result)


@router.post("/analyze-image", response_model=schemas.AIAnalysisResponse)
async def analyze_image_upload(
    file: UploadFile = File(...),
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

    result = _run_or_raise(
        symbol=symbol,
        timeframe=timeframe,
        prompt=prompt or None,
        image_bytes=image_bytes,
        image_mime=file.content_type,
        price_context=_live_context(symbol, timeframe),
    )
    return _persist_analysis(db, current_user["user_id"], symbol, timeframe, prompt or None, result)


@router.get("/signal-of-the-day", response_model=schemas.AIAnalysisResponse)
async def signal_of_the_day(
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
    if existing:
        return existing

    # Build a multi-market context and let the model pick one setup
    sections = []
    for candidate in SOTD_CANDIDATES:
        context = _live_context(candidate, "H4")
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
        "formatted exactly like: 'Selected market: <SYMBOL>'."
    )
    result = _run_or_raise(symbol="MULTI", timeframe="H4", prompt=selection_prompt, price_context="\n\n".join(sections))

    chosen = "EURUSD"
    for reason in result.get("reasoning", []):
        if reason.lower().startswith("selected market:"):
            chosen = reason.split(":", 1)[1].strip().upper() or chosen
            break

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
