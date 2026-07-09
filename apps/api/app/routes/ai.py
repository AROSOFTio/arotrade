from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.config import settings
import json

router = APIRouter()


@router.post("/analyze", response_model=schemas.AIAnalysisResponse)
async def analyze_chart(
    request: schemas.AIAnalysisRequest,
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Analyze a trading chart using Gemini AI."""
    if not settings.GEMINI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured"
        )

    # Create AI analysis record
    analysis = models.AIAnalysis(
        user_id=current_user["user_id"],
        symbol=request.symbol,
        timeframe=request.timeframe,
        image_url=request.image_url,
        prompt=request.prompt
    )

    # TODO: Call Gemini API to analyze
    # For now, return mock analysis
    analysis.bias = "bullish"
    analysis.signal = "buy"
    analysis.confidence = 68
    analysis.entry_min = 2345.2
    analysis.entry_max = 2348.1
    analysis.stop_loss = 2338.5
    analysis.take_profit_1 = 2355.0
    analysis.take_profit_2 = 2364.0
    analysis.take_profit_3 = 2372.0
    analysis.risk_reward = 2.3
    analysis.reasoning = [
        "Market structure is bullish",
        "Price reacted from demand zone",
        "RSI momentum supports continuation"
    ]
    analysis.invalidation = "Signal becomes invalid below 2338.5"
    analysis.news_warning = "Check high-impact USD news before execution"
    analysis.risk_warning = "Use maximum 1% account risk"

    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    return analysis


@router.post("/analyze-image")
async def analyze_image_upload(
    file: UploadFile = File(...),
    symbol: str = Form(...),
    timeframe: str = Form(...),
    prompt: str = Form(default="Analyze this chart"),
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Analyze an uploaded chart image."""
    if not settings.GEMINI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured"
        )

    # TODO: Save uploaded image and process
    # For now, call analyze endpoint with placeholder
    request = schemas.AIAnalysisRequest(
        symbol=symbol,
        timeframe=timeframe,
        image_url="",
        prompt=prompt
    )

    return await analyze_chart(request, current_user, db)


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
    ).offset(skip).limit(limit).all()

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
