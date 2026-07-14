from fastapi import APIRouter
from datetime import datetime
from sqlalchemy import text
from app import models
from app.schemas import HealthResponse, AIHealthResponse
from app.config import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    import redis
    from app.database import SessionLocal
    
    r = redis.Redis.from_url(settings.REDIS_URL)
    db = SessionLocal()
    
    status_str = "healthy"
    details = {}
    
    try:
        # Check database connection
        db.execute(text("SELECT 1"))
        details["database"] = "connected"
    except Exception as exc:
        status_str = "degraded"
        details["database"] = f"failed: {exc}"
        
    try:
        # Check Redis connection
        r.ping()
        details["redis"] = "connected"
    except Exception as exc:
        status_str = "degraded"
        details["redis"] = f"failed: {exc}"
        
    db.close()
    
    return {
        "status": status_str,
        "version": "1.0.0",
        "timestamp": datetime.utcnow(),
        "details": details
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
    """Check execution engine health truthfully."""
    import redis
    from app.database import SessionLocal
    
    r = redis.Redis.from_url(settings.REDIS_URL)
    db = SessionLocal()
    
    try:
        # Check active deployed accounts
        deployed_accounts = db.query(models.BrokerAccount).filter(
            models.BrokerAccount.is_active == True,
            models.BrokerAccount.connection_state == "deployed",
            models.BrokerAccount.metaapi_account_id.isnot(None),
        ).all()
        metaapi_status = "disconnected"
        if deployed_accounts:
            metaapi_status = "connected"

        # Check reconciliation mismatches
        reconciliation_mismatches = db.query(models.Trade).filter(
            models.Trade.reconciliation_status == "uncertain_closed"
        ).count()
        
        # Check heartbeats from Redis
        worker_hb = r.get("worker:heartbeat")
        beat_hb = r.get("beat:heartbeat")
        streamer_hb = r.get("streamer:heartbeat")
        
        worker_last = worker_hb.decode("utf-8") if worker_hb else None
        beat_last = beat_hb.decode("utf-8") if beat_hb else None
        streamer_last = streamer_hb.decode("utf-8") if streamer_hb else None

        # Calculate quote age
        latest_quote_ts = r.get("quote:latest:timestamp")
        quote_age = None
        if latest_quote_ts:
            try:
                qt = datetime.fromisoformat(latest_quote_ts.decode("utf-8"))
                quote_age = (datetime.utcnow() - qt).total_seconds()
            except Exception:
                pass

        # Determine overall status
        hb_stale = False
        now_ts = datetime.utcnow()
        for hb_str in (worker_last, beat_last, streamer_last):
            if hb_str:
                try:
                    hb_dt = datetime.fromisoformat(hb_str)
                    if (now_ts - hb_dt).total_seconds() > 60.0:
                        hb_stale = True
                except Exception:
                    pass
            else:
                hb_stale = True

        status_str = "operational"
        if hb_stale or metaapi_status == "disconnected" or reconciliation_mismatches > 0:
            status_str = "degraded"

        return {
            "status": status_str,
            "paper_trading": settings.PAPER_TRADING_ENABLED,
            "live_trading": settings.ENABLE_LIVE_TRADING,
            "metaapi_connectivity": metaapi_status,
            "reconciliation_mismatches": reconciliation_mismatches,
            "heartbeats": {
                "worker": worker_last or "missing",
                "beat": beat_last or "missing",
                "streamer": streamer_last or "missing",
            },
            "latest_quote_age_seconds": round(quote_age, 1) if quote_age is not None else None,
        }
    finally:
        db.close()
