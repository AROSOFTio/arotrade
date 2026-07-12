"""Scanner profile management API routes.

Endpoints:
  POST   /api/scanner/profiles              Create a scanner profile
  GET    /api/scanner/profiles              List all user profiles
  GET    /api/scanner/profiles/{id}         Get one profile
  PATCH  /api/scanner/profiles/{id}         Update profile
  DELETE /api/scanner/profiles/{id}         Delete profile
  POST   /api/scanner/profiles/{id}/enable  Enable scanning
  POST   /api/scanner/profiles/{id}/disable Disable scanning
  POST   /api/scanner/profiles/{id}/scan    Trigger on-demand scan
  GET    /api/scanner/strategies            List available strategies
  GET    /api/scanner/status               Global scanner status
"""

from __future__ import annotations

import logging
from datetime import datetime, UTC
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal
from app.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class ScannerProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    broker_account_id: Optional[int] = None
    execution_mode: str = Field("paper", pattern="^(paper|broker_demo|live)$")
    symbols: Optional[list[str]] = None
    timeframes: Optional[list[str]] = None
    active_strategy_ids: Optional[list[str]] = None
    minimum_confidence: float = Field(70.0, ge=0, le=100)
    minimum_risk_reward: float = Field(1.5, ge=0.1)
    max_spread_points: Optional[float] = None
    maximum_signal_age_minutes: int = Field(240, ge=30, le=1440)
    risk_percent: float = Field(0.5, ge=0.01, le=5.0)
    news_block_before_minutes: int = Field(30, ge=0, le=120)
    news_block_after_minutes: int = Field(30, ge=0, le=120)
    approval_required: bool = True


class ScannerProfileUpdate(BaseModel):
    name: Optional[str] = None
    broker_account_id: Optional[int] = None
    execution_mode: Optional[str] = Field(None, pattern="^(paper|broker_demo|live)$")
    symbols: Optional[list[str]] = None
    timeframes: Optional[list[str]] = None
    active_strategy_ids: Optional[list[str]] = None
    minimum_confidence: Optional[float] = None
    minimum_risk_reward: Optional[float] = None
    max_spread_points: Optional[float] = None
    maximum_signal_age_minutes: Optional[int] = None
    risk_percent: Optional[float] = None
    news_block_before_minutes: Optional[int] = None
    news_block_after_minutes: Optional[int] = None
    approval_required: Optional[bool] = None


def _serialize_profile(profile: models.ScannerProfile) -> dict:
    return {
        "id": profile.id,
        "user_id": profile.user_id,
        "broker_account_id": profile.broker_account_id,
        "name": profile.name,
        "execution_mode": profile.execution_mode,
        "symbols": profile.symbols or [],
        "timeframes": profile.timeframes or [],
        "active_strategy_ids": profile.active_strategy_ids or [],
        "minimum_confidence": profile.minimum_confidence,
        "minimum_risk_reward": profile.minimum_risk_reward,
        "max_spread_points": profile.max_spread_points,
        "maximum_signal_age_minutes": profile.maximum_signal_age_minutes,
        "risk_percent": profile.risk_percent,
        "news_block_before_minutes": profile.news_block_before_minutes,
        "news_block_after_minutes": profile.news_block_after_minutes,
        "scan_enabled": profile.scan_enabled,
        "approval_required": profile.approval_required,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/profiles", status_code=status.HTTP_201_CREATED)
def create_profile(
    request: ScannerProfileCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Create a new scanner profile."""
    # Validate broker account ownership
    if request.broker_account_id:
        account = db.query(models.BrokerAccount).filter(
            models.BrokerAccount.id == request.broker_account_id,
            models.BrokerAccount.user_id == user.id,
        ).first()
        if not account:
            raise HTTPException(status_code=404, detail="Broker account not found")

        # Enforce mode/account-type consistency
        if request.execution_mode == "live" and account.account_type != models.TradingMode.LIVE:
            raise HTTPException(
                status_code=400,
                detail="Execution mode 'live' requires a live broker account."
            )
        if request.execution_mode == "broker_demo" and account.account_type != models.TradingMode.DEMO:
            raise HTTPException(
                status_code=400,
                detail="Execution mode 'broker_demo' requires a demo broker account."
            )

    profile = models.ScannerProfile(
        user_id=user.id,
        **request.model_dump(),
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    return {"success": True, "profile": _serialize_profile(profile)}


@router.get("/profiles")
def list_profiles(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """List all scanner profiles for the current user."""
    profiles = (
        db.query(models.ScannerProfile)
        .filter(models.ScannerProfile.user_id == user.id)
        .order_by(models.ScannerProfile.created_at.desc())
        .all()
    )
    return {
        "success": True,
        "profiles": [_serialize_profile(p) for p in profiles],
        "total": len(profiles),
    }


@router.get("/profiles/{profile_id}")
def get_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    profile = db.query(models.ScannerProfile).filter(
        models.ScannerProfile.id == profile_id,
        models.ScannerProfile.user_id == user.id,
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Scanner profile not found")
    return {"success": True, "profile": _serialize_profile(profile)}


@router.patch("/profiles/{profile_id}")
def update_profile(
    profile_id: int,
    request: ScannerProfileUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    profile = db.query(models.ScannerProfile).filter(
        models.ScannerProfile.id == profile_id,
        models.ScannerProfile.user_id == user.id,
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Scanner profile not found")

    for key, value in request.model_dump(exclude_none=True).items():
        setattr(profile, key, value)

    db.commit()
    db.refresh(profile)
    return {"success": True, "profile": _serialize_profile(profile)}


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_200_OK)
def delete_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    profile = db.query(models.ScannerProfile).filter(
        models.ScannerProfile.id == profile_id,
        models.ScannerProfile.user_id == user.id,
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Scanner profile not found")

    # Disable first, then delete
    if profile.scan_enabled:
        profile.scan_enabled = False
        db.commit()

    db.delete(profile)
    db.commit()
    return {"success": True, "message": "Scanner profile deleted"}


@router.post("/profiles/{profile_id}/enable")
def enable_scanning(
    profile_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Enable automatic scanning for this profile."""
    profile = db.query(models.ScannerProfile).filter(
        models.ScannerProfile.id == profile_id,
        models.ScannerProfile.user_id == user.id,
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Scanner profile not found")

    if not profile.symbols or not profile.timeframes:
        raise HTTPException(
            status_code=400,
            detail="Cannot enable scanner: at least one symbol and one timeframe must be configured"
        )

    if not profile.broker_account_id and profile.execution_mode != "paper":
        raise HTTPException(
            status_code=400,
            detail="Cannot enable scanner: broker account is required for non-paper execution modes"
        )

    profile.scan_enabled = True
    db.commit()
    db.refresh(profile)
    return {"success": True, "profile": _serialize_profile(profile)}


@router.post("/profiles/{profile_id}/disable")
def disable_scanning(
    profile_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Pause automatic scanning for this profile."""
    profile = db.query(models.ScannerProfile).filter(
        models.ScannerProfile.id == profile_id,
        models.ScannerProfile.user_id == user.id,
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Scanner profile not found")

    profile.scan_enabled = False
    db.commit()
    db.refresh(profile)
    return {"success": True, "profile": _serialize_profile(profile)}


@router.post("/profiles/{profile_id}/scan")
def trigger_scan(
    profile_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Trigger an immediate on-demand scan for this profile."""
    profile = db.query(models.ScannerProfile).filter(
        models.ScannerProfile.id == profile_id,
        models.ScannerProfile.user_id == user.id,
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Scanner profile not found")

    try:
        from app.workers.scanner_tasks import run_single_profile
        task = run_single_profile.delay(profile_id)
        return {
            "success": True,
            "message": "Scan triggered",
            "task_id": str(task.id),
        }
    except Exception as exc:
        logger.warning("Could not queue scan task (Celery may be unavailable): %s", exc)
        # Fall back to synchronous scan
        try:
            from app.workers.scanner_tasks import _scan_profile
            _scan_profile(db, profile)
            return {"success": True, "message": "Scan completed synchronously"}
        except Exception as exc2:
            raise HTTPException(status_code=500, detail=str(exc2))


@router.get("/strategies")
def list_strategies(
    user: models.User = Depends(get_current_user),
):
    """List all available scanner strategies."""
    from app.services.scanner.strategies import list_strategies as _list
    return {"success": True, "strategies": _list()}


@router.get("/status")
def scanner_status(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Global scanner status for this user."""
    from app.config import settings

    profiles = (
        db.query(models.ScannerProfile)
        .filter(models.ScannerProfile.user_id == user.id)
        .all()
    )

    active_profiles = [p for p in profiles if p.scan_enabled]
    total_symbols = sum(len(p.symbols or []) for p in active_profiles)
    total_timeframes = sum(len(p.timeframes or []) for p in active_profiles)

    # Recent auto signals
    from datetime import timedelta
    recent_cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24)
    recent_signals = (
        db.query(models.Signal)
        .filter(
            models.Signal.user_id == user.id,
            models.Signal.source == "auto",
            models.Signal.created_at >= recent_cutoff,
        )
        .count()
    )

    return {
        "success": True,
        "scanner_enabled": settings.SCANNER_ENABLED,
        "scan_interval_seconds": settings.SCANNER_DEFAULT_INTERVAL_SECONDS,
        "total_profiles": len(profiles),
        "active_profiles": len(active_profiles),
        "total_symbols_watched": total_symbols,
        "total_timeframes_watched": total_timeframes,
        "signals_last_24h": recent_signals,
    }
