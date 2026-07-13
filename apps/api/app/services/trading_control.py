"""Platform and user execution controls.

The infrastructure environment remains an emergency layer only; normal owner
control lives in the database and is cached best-effort in Redis.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app import models
from app.config import settings

try:
    import redis
except Exception:  # pragma: no cover - redis is optional at import time
    redis = None


CONTROL_KEY = "platform_trading_control"
CACHE_KEY = "arotrade:platform_trading_control"
CACHE_SECONDS = 60


DEFAULT_CONTROL: dict[str, bool] = {
    "live_trading_allowed": True,
    "new_live_entries_allowed": True,
    "broker_demo_trading_allowed": True,
    "paper_trading_allowed": True,
    "live_position_management_allowed": True,
}


def _redis_client():
    if redis is None:
        return None
    try:
        return redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
    except Exception:
        return None


def _cache_get() -> dict[str, Any] | None:
    client = _redis_client()
    if not client:
        return None
    try:
        raw = client.get(CACHE_KEY)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _cache_set(value: dict[str, Any]) -> None:
    client = _redis_client()
    if not client:
        return
    try:
        client.setex(CACHE_KEY, CACHE_SECONDS, json.dumps(value))
    except Exception:
        return


def _normalize_control(value: dict[str, Any] | None) -> dict[str, Any]:
    control = dict(DEFAULT_CONTROL)
    if isinstance(value, dict):
        for key in DEFAULT_CONTROL:
            if key in value:
                control[key] = bool(value[key])
        for key in ("updated_at", "updated_by", "reason", "request_id"):
            if key in value:
                control[key] = value[key]
    return control


def get_platform_control(db: Session) -> dict[str, Any]:
    cached = _cache_get()
    if cached:
        return _normalize_control(cached)

    setting = db.query(models.AdminSetting).filter(models.AdminSetting.key == CONTROL_KEY).first()
    if not setting:
        control = _normalize_control({
            **DEFAULT_CONTROL,
            "updated_at": datetime.utcnow().isoformat(),
            "updated_by": None,
            "reason": "Initial default control state",
            "request_id": None,
        })
        setting = models.AdminSetting(
            key=CONTROL_KEY,
            value=control,
            description="Owner-controlled platform trading permissions",
        )
        db.add(setting)
        db.commit()
        db.refresh(setting)
    control = _normalize_control(setting.value)
    _cache_set(control)
    return control


def update_platform_control(
    db: Session,
    *,
    admin_user: models.User,
    updates: dict[str, bool],
    reason: str,
    ip_address: str | None,
    user_agent: str | None,
    request_id: str | None = None,
) -> dict[str, Any]:
    previous = get_platform_control(db)
    next_state = _normalize_control({**previous, **updates})
    next_state.update({
        "updated_at": datetime.utcnow().isoformat(),
        "updated_by": admin_user.id,
        "reason": reason,
        "request_id": request_id or str(uuid4()),
    })

    setting = db.query(models.AdminSetting).filter(models.AdminSetting.key == CONTROL_KEY).first()
    if not setting:
        setting = models.AdminSetting(
            key=CONTROL_KEY,
            value=next_state,
            description="Owner-controlled platform trading permissions",
        )
        db.add(setting)
    else:
        setting.value = next_state

    db.add(models.AuditLog(
        user_id=admin_user.id,
        action="platform_live_control_update",
        resource="admin_setting",
        resource_id=setting.id,
        changes={
            "request_id": next_state["request_id"],
            "reason": reason,
            "previous": {key: previous.get(key) for key in DEFAULT_CONTROL},
            "new": {key: next_state.get(key) for key in DEFAULT_CONTROL},
        },
        ip_address=ip_address,
        user_agent=user_agent,
    ))
    db.commit()
    db.refresh(setting)
    _cache_set(next_state)
    return next_state


def platform_health_summary(db: Session) -> dict[str, Any]:
    live_accounts = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.account_type == models.TradingMode.LIVE,
        models.BrokerAccount.is_active == True,  # noqa: E712
        models.BrokerAccount.metaapi_account_id.isnot(None),
        models.BrokerAccount.connection_state == "deployed",
    ).count()
    demo_accounts = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.account_type == models.TradingMode.DEMO,
        models.BrokerAccount.is_active == True,  # noqa: E712
        models.BrokerAccount.metaapi_account_id.isnot(None),
        models.BrokerAccount.connection_state == "deployed",
    ).count()
    open_live = db.query(models.Trade).filter(
        models.Trade.mode == models.TradingMode.LIVE,
        models.Trade.status == models.TradeStatus.OPEN,
    ).count()
    pending_live = db.query(models.Trade).filter(
        models.Trade.mode == models.TradingMode.LIVE,
        models.Trade.execution_status.in_(("queued", "pending", "submitted")),
    ).count()
    unknown_states = db.query(models.Trade).filter(
        models.Trade.mode == models.TradingMode.LIVE,
        models.Trade.execution_status.is_(None),
    ).count()
    return {
        "connected_live_accounts": live_accounts,
        "connected_demo_accounts": demo_accounts,
        "open_live_positions": open_live,
        "pending_live_orders": pending_live,
        "unknown_execution_states": unknown_states,
        "reconciliation_mismatches": 0,
        "health": {
            "reconciliation": "not_configured",
            "execution_worker": "available",
            "market_quotes": "available",
            "metaapi": "configured" if settings.METAAPI_TOKEN else "missing_token",
            "risk_engine": "available",
        },
    }


def live_entry_block_reason(control: dict[str, Any]) -> str | None:
    if control.get("emergency_stop", False):
        return "Emergency stop is active. New live orders are blocked."
    if control.get("close_only_mode", False):
        return "Close-only mode is active. New live entries are blocked."
    if not getattr(settings, "LIVE_TRADING_ALLOWED", True):
        return "LIVE_TRADING_ALLOWED=false in platform configuration."
    if not getattr(settings, "NEW_LIVE_ENTRIES_ALLOWED", True):
        return "NEW_LIVE_ENTRIES_ALLOWED=false in platform configuration."
    if not control.get("live_trading_allowed", True):
        return "Platform owner has paused live trading. Your live preference remains saved."
    if not control.get("new_live_entries_allowed", True):
        return "Platform owner has paused new live entries. Existing live-position management remains available."
    return None


def paper_block_reason(control: dict[str, Any]) -> str | None:
    if not settings.PAPER_TRADING_ENABLED:
        return "Paper trading is disabled by infrastructure configuration."
    if not control.get("paper_trading_allowed", True):
        return "Paper trading is paused by the platform owner."
    return None


def broker_demo_block_reason(control: dict[str, Any]) -> str | None:
    if not control.get("broker_demo_trading_allowed", True):
        return "Broker-demo trading is paused by the platform owner."
    return None


def execution_status_for_user(db: Session, user: models.User) -> dict[str, Any]:
    control = get_platform_control(db)
    active_accounts = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.user_id == user.id,
        models.BrokerAccount.is_active == True,  # noqa: E712
        models.BrokerAccount.metaapi_account_id.isnot(None),
    ).all()
    deployed_live = [
        account for account in active_accounts
        if account.account_type == models.TradingMode.LIVE and account.connection_state == "deployed"
    ]
    deployed_demo = [
        account for account in active_accounts
        if account.account_type == models.TradingMode.DEMO and account.connection_state == "deployed"
    ]
    risk_configured = user.default_risk_percent > 0 and user.max_daily_loss_percent > 0 and user.max_open_trades > 0

    live_reasons: list[str] = []
    platform_reason = live_entry_block_reason(control)
    if platform_reason:
        live_reasons.append(platform_reason)
    if not user.enable_live_trading:
        live_reasons.append("Live trading is off in your user preferences.")
    if not user.accepted_live_disclaimer:
        live_reasons.append("Live-trading risk disclosure has not been accepted.")
    if not deployed_live:
        live_reasons.append("No verified live broker account is deployed and connected.")
    if not risk_configured:
        live_reasons.append("Risk controls are incomplete.")

    return {
        "paper_trading": {
            "platform_allowed": paper_block_reason(control) is None,
            "available": paper_block_reason(control) is None,
            "reason": paper_block_reason(control),
        },
        "broker_demo_trading": {
            "platform_allowed": broker_demo_block_reason(control) is None,
            "connected_accounts": len(deployed_demo),
            "available": broker_demo_block_reason(control) is None and bool(deployed_demo),
            "reason": broker_demo_block_reason(control),
        },
        "live_trading": {
            "user_preference": user.enable_live_trading,
            "risk_disclosure": user.accepted_live_disclaimer,
            "platform_permission": bool(control.get("live_trading_allowed", True)),
            "new_entries_allowed": bool(control.get("new_live_entries_allowed", True)),
            "live_account_verified": bool(deployed_live),
            "broker_connection": bool(deployed_live),
            "mfa_status": "not_configured",
            "risk_control_status": "configured" if risk_configured else "incomplete",
            "final_eligibility": not live_reasons,
            "reasons": live_reasons,
        },
    }
