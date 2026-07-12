from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app import models, schemas
from app.database import get_db
from app.services import trading_control

router = APIRouter()


async def check_admin(
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db)
):
    """Check if current user is admin."""
    user = db.query(models.User).filter(models.User.id == current_user["user_id"]).first()

    if not user or user.role != models.UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    return user


def _request_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else None


@router.get("/dashboard", dependencies=[Depends(check_admin)])
async def admin_dashboard(
    current_user: dict = Depends(check_admin),
    db: Session = Depends(get_db)
):
    """Get admin dashboard stats."""
    total_users = db.query(models.User).count()
    active_users = db.query(models.User).filter(models.User.is_active == True).count()

    # Last 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    signals = db.query(models.Signal).filter(
        models.Signal.created_at >= thirty_days_ago
    ).count()

    demo_trades = db.query(models.Trade).filter(
        models.Trade.mode == models.TradingMode.DEMO,
        models.Trade.created_at >= thirty_days_ago
    ).count()

    live_trades = db.query(models.Trade).filter(
        models.Trade.mode == models.TradingMode.LIVE,
        models.Trade.created_at >= thirty_days_ago
    ).count()

    failed_trades = db.query(models.Trade).filter(
        models.Trade.status == models.TradeStatus.CANCELLED,
        models.Trade.created_at >= thirty_days_ago
    ).count()

    risk_violations = db.query(models.RiskViolation).filter(
        models.RiskViolation.created_at >= thirty_days_ago
    ).count()

    return schemas.DashboardStats(
        total_users=total_users,
        active_users=active_users,
        total_signals=signals,
        demo_trades=demo_trades,
        live_trades=live_trades,
        failed_trades=failed_trades,
        risk_violations=risk_violations,
        api_errors=0  # TODO: Track API errors
    )


@router.get("/live-control", dependencies=[Depends(check_admin)])
async def get_live_control(
    current_user: models.User = Depends(check_admin),
    db: Session = Depends(get_db),
):
    control = trading_control.get_platform_control(db)
    summary = trading_control.platform_health_summary(db)
    recent_audits = db.query(models.AuditLog).filter(
        models.AuditLog.action == "platform_live_control_update"
    ).order_by(models.AuditLog.created_at.desc()).limit(20).all()
    return {
        "control": control,
        "account_summary": {key: value for key, value in summary.items() if key != "health"},
        "health": summary["health"],
        "recent_audit": recent_audits,
    }


@router.patch("/live-control", dependencies=[Depends(check_admin)])
async def update_live_control(
    payload: schemas.PlatformTradingControlUpdate,
    request: Request,
    current_user: models.User = Depends(check_admin),
    db: Session = Depends(get_db),
):
    updates = payload.model_dump(
        exclude_none=True,
        exclude={"reason", "confirmation"},
    )
    control = trading_control.update_platform_control(
        db,
        admin_user=current_user,
        updates=updates,
        reason=payload.reason.strip(),
        ip_address=_request_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_id=request.headers.get("x-request-id"),
    )
    summary = trading_control.platform_health_summary(db)
    return {
        "control": control,
        "account_summary": {key: value for key, value in summary.items() if key != "health"},
        "health": summary["health"],
    }


@router.get("/audit-logs", dependencies=[Depends(check_admin)])
async def get_audit_logs(
    current_user: dict = Depends(check_admin),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """Get audit logs."""
    logs = db.query(models.AuditLog).order_by(
        models.AuditLog.created_at.desc()
    ).offset(skip).limit(limit).all()

    return logs


@router.get("/users", dependencies=[Depends(check_admin)])
async def list_all_users(
    current_user: dict = Depends(check_admin),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """List all users."""
    users = db.query(models.User).offset(skip).limit(limit).all()

    return users


@router.post("/users/{user_id}/disable", dependencies=[Depends(check_admin)])
async def disable_user(
    user_id: int,
    current_user: dict = Depends(check_admin),
    db: Session = Depends(get_db)
):
    """Disable a user account."""
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    user.is_active = False
    db.commit()
    db.refresh(user)

    # Log audit
    audit = models.AuditLog(
        user_id=current_user.id,
        action="disable_user",
        resource="user",
        resource_id=user_id,
        changes={"is_active": False}
    )
    db.add(audit)
    db.commit()

    return {"message": "User disabled"}


@router.post("/users/{user_id}/enable-live-trading", dependencies=[Depends(check_admin)])
async def enable_user_live_trading(
    user_id: int,
    current_user: dict = Depends(check_admin),
    db: Session = Depends(get_db)
):
    """Enable live trading for a user."""
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    previous_mode = user.trading_mode.value if user.trading_mode else None
    user.enable_live_trading = True
    user.accepted_live_disclaimer = True
    user.trading_mode = models.TradingMode.LIVE
    db.commit()

    # Log audit
    audit = models.AuditLog(
        user_id=current_user.id,
        action="enable_live_trading",
        resource="user",
        resource_id=user_id,
        changes={
            "enable_live_trading": True,
            "accepted_live_disclaimer": True,
            "trading_mode": {
                "from": previous_mode,
                "to": user.trading_mode.value,
            },
        }
    )
    db.add(audit)
    db.commit()

    return {"message": "Live trading enabled"}


@router.get("/signals", dependencies=[Depends(check_admin)])
async def list_all_signals(
    current_user: dict = Depends(check_admin),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """List all signals (admin)."""
    signals = db.query(models.Signal).offset(skip).limit(limit).all()

    return signals


@router.get("/trades", dependencies=[Depends(check_admin)])
async def list_all_trades(
    current_user: dict = Depends(check_admin),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """List all trades (admin)."""
    trades = db.query(models.Trade).offset(skip).limit(limit).all()

    return trades


@router.get("/risk-violations", dependencies=[Depends(check_admin)])
async def list_risk_violations(
    current_user: dict = Depends(check_admin),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """List risk violations."""
    violations = db.query(models.RiskViolation).order_by(
        models.RiskViolation.created_at.desc()
    ).offset(skip).limit(limit).all()

    return violations
