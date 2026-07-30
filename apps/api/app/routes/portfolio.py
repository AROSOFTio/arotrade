from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.services.mt5_bridge.store import get_account_snapshot

router = APIRouter()


def _enum_value(value: Any) -> str:
    return getattr(value, "value", value) or ""


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _position_profit(position: dict[str, Any]) -> float:
    for key in ("profit", "unrealized_profit", "unrealizedProfit", "floating_profit", "floatingProfit"):
        if key in position:
            return _to_float(position.get(key))
    return 0.0


def _position_volume(position: dict[str, Any]) -> float:
    for key in ("volume", "lots", "currentVolume"):
        if key in position:
            return _to_float(position.get(key))
    return 0.0


def _position_symbol(position: dict[str, Any]) -> str:
    return str(position.get("symbol") or position.get("broker_symbol") or position.get("brokerSymbol") or "UNKNOWN").upper()


def build_portfolio_summary(user_id: int, db: Session) -> dict[str, Any]:
    accounts = db.query(models.BrokerAccount).filter(
        models.BrokerAccount.user_id == user_id,
        models.BrokerAccount.is_active == True,
    ).all()
    trades = db.query(models.Trade).filter(models.Trade.user_id == user_id).all()

    total_balance = sum(_to_float(account.balance) for account in accounts)
    currency = next((account.currency for account in accounts if account.currency), "USD")
    realized_pnl = sum(_to_float(trade.profit_loss) for trade in trades if _enum_value(trade.status) == "closed")
    open_trade_count = sum(1 for trade in trades if _enum_value(trade.status) == "open")
    closed = [trade for trade in trades if _enum_value(trade.status) == "closed"]
    wins = sum(1 for trade in closed if _to_float(trade.profit_loss) > 0)

    exposure_by_symbol: dict[str, dict[str, Any]] = defaultdict(lambda: {"symbol": "", "volume": 0.0, "floating_pnl": 0.0, "positions": 0})
    account_rows = []
    floating_pnl = 0.0
    live_positions = 0

    for account in accounts:
        snapshot = get_account_snapshot(account.id) if account.broker == "direct-mt5" or account.connection_state == "direct_connected" else None
        positions = snapshot.get("positions", []) if isinstance(snapshot, dict) and isinstance(snapshot.get("positions"), list) else []
        account_floating = sum(_position_profit(position) for position in positions if isinstance(position, dict))
        floating_pnl += account_floating
        live_positions += len(positions)
        for position in positions:
            if not isinstance(position, dict):
                continue
            symbol = _position_symbol(position)
            row = exposure_by_symbol[symbol]
            row["symbol"] = symbol
            row["volume"] += _position_volume(position)
            row["floating_pnl"] += _position_profit(position)
            row["positions"] += 1
        account_rows.append({
            "id": account.id,
            "name": account.name or account.account_id,
            "broker": account.broker,
            "account_id": account.account_id,
            "account_type": _enum_value(account.account_type),
            "balance": round(_to_float(account.balance), 2),
            "currency": account.currency or currency,
            "connection_state": account.connection_state,
            "provider": "direct-mt5" if account.broker == "direct-mt5" or account.connection_state == "direct_connected" else "metaapi-optional",
            "positions": len(positions),
            "floating_pnl": round(account_floating, 2),
            "last_snapshot_at": snapshot.get("received_at") if isinstance(snapshot, dict) else None,
        })

    exposure_rows = sorted(exposure_by_symbol.values(), key=lambda item: abs(item["floating_pnl"]), reverse=True)
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "currency": currency,
        "total_balance": round(total_balance, 2),
        "equity_estimate": round(total_balance + floating_pnl, 2),
        "realized_pnl": round(realized_pnl, 2),
        "floating_pnl": round(floating_pnl, 2),
        "account_count": len(accounts),
        "open_trade_count": open_trade_count,
        "live_position_count": live_positions,
        "closed_trade_count": len(closed),
        "win_rate": round((wins / len(closed)) * 100, 2) if closed else 0.0,
        "accounts": account_rows,
        "exposure_by_symbol": [
            {**row, "volume": round(row["volume"], 4), "floating_pnl": round(row["floating_pnl"], 2)}
            for row in exposure_rows
        ],
    }


@router.get("/summary")
async def portfolio_summary(
    current_user: dict = Depends(__import__('app.auth', fromlist=['get_current_user']).get_current_user),
    db: Session = Depends(get_db),
):
    return build_portfolio_summary(current_user["user_id"], db)
