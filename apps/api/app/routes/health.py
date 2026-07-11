from fastapi import APIRouter
from datetime import datetime
from app.schemas import HealthResponse, AIHealthResponse
from app.config import settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.utcnow()
    }


@router.get("/version")
async def version():
    """Get API version."""
    return {
        "version": "1.0.0",
        "app": "AroTrade AI",
        "environment": settings.APP_ENV
    }


@router.get("/ai/health", response_model=AIHealthResponse)
async def ai_health():
    """Check AI service health."""
    gemini_available = bool(settings.GEMINI_API_KEY)

    return {
        "status": "operational" if gemini_available else "unavailable",
        "provider": "Gemini",
        "model": settings.GEMINI_MODEL,
        "is_available": gemini_available,
        "timestamp": datetime.utcnow()
    }


@router.get("/execution/health")
async def execution_health():
    """Check execution engine health."""
    deriv_available = bool(settings.DERIV_APP_ID)

    return {
        "status": "paper_ready" if settings.PAPER_TRADING_ENABLED else "disabled",
        "paper_trading": settings.PAPER_TRADING_ENABLED,
        "live_trading": settings.ENABLE_LIVE_TRADING,
        "deriv_available": deriv_available,
        "live_broker_adapter": bool(settings.METAAPI_TOKEN),
    }
