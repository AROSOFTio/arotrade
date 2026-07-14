"""Comprehensive risk engine for pre-execution validation.

This runs immediately before any broker-demo or live order submission.
It is the final backend gate: if any check fails, the order is blocked.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.services import news, trading_control

logger = logging.getLogger(__name__)

# Maximum entry distance for JUMP IN NOW.
JUMP_IN_TOLERANCE_PCT = 0.003  # 0.3%

ACTIVE_INTENT_STATUSES = {
    "CREATED",
    "VALIDATING",
    "SUBMITTING",
    "BROKER_ACCEPTED",
    "FILLED",
    "UNCERTAIN",
}


@dataclass
class RiskCheckResult:
    approved: bool = True
    reasons: list[str] = field(default_factory=list)

    def block(self, reason: str) -> None:
        self.approved = False
        self.reasons.append(reason)


def _quote_float(quote: dict, *keys: str) -> float:
    for key in keys:
        value = quote.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _value(value: object) -> str:
    return str(getattr(value, "value", value) or "").lower()


def _symbol_for_risk(signal: Optional[models.Signal], symbol: Optional[str]) -> str:
    value = symbol
    if signal is not None:
        value = value or getattr(signal, "broker_symbol", None) or getattr(signal, "canonical_symbol", None) or signal.symbol
    return str(value or "").strip().upper()


def _spread_points(quote: dict, symbol_point: Optional[float]) -> float | None:
    if symbol_point is None or symbol_point <= 0:
        return None
    bid = _quote_float(quote, "bid", "brokerBid")
    ask = _quote_float(quote, "ask", "brokerAsk")
    if bid > 0 and ask > 0 and ask >= bid:
        return (ask - bid) / symbol_point
    spread = _quote_float(quote, "spread")
    if spread > 0:
        return spread / symbol_point
    return None


def _risk_reward_for_signal(signal: models.Signal, observed_price: float) -> float | None:
    stop_loss = float(signal.stop_loss or 0.0)
    take_profit = float(signal.take_profit_1 or 0.0)
    direction = str(signal.signal_type or "").lower()
    if observed_price <= 0 or stop_loss <= 0 or take_profit <= 0:
        return None
    if direction == "buy" and stop_loss < observed_price < take_profit:
        return (take_profit - observed_price) / (observed_price - stop_loss)
    if direction == "sell" and take_profit < observed_price < stop_loss:
        return (observed_price - take_profit) / (stop_loss - observed_price)
    return None


def _open_symbol_trade_count(
    db: Session,
    *,
    user_id: int,
    broker_account_id: int,
    symbol: str,
    execution_mode: str,
) -> int:
    if not symbol:
        return 0
    mode_filter = [execution_mode] if execution_mode in ("live", "broker_demo") else ["live", "broker_demo"]
    return db.query(models.Trade).filter(
        models.Trade.user_id == user_id,
        models.Trade.broker_account_id == broker_account_id,
        models.Trade.status == models.TradeStatus.OPEN,
        models.Trade.execution_mode.in_(mode_filter),
        or_(
            func.upper(models.Trade.broker_symbol) == symbol,
            func.upper(models.Trade.symbol) == symbol,
        ),
    ).count()


def _active_signal_intent_exists(db: Session, signal_id: int, execution_mode: str) -> bool:
    existing_intent = db.query(models.ExecutionIntent).filter(
        models.ExecutionIntent.signal_id == signal_id,
        models.ExecutionIntent.execution_mode == execution_mode,
        models.ExecutionIntent.status.in_(ACTIVE_INTENT_STATUSES),
    ).first()
    return existing_intent is not None


def _parse_news_time(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _news_blackout_reason(signal: models.Signal, now: datetime) -> str | None:
    profile = getattr(signal, "scanner_profile", None)
    if not profile:
        return None

    before_minutes = int(getattr(profile, "news_block_before_minutes", 0) or 0)
    after_minutes = int(getattr(profile, "news_block_after_minutes", 0) or 0)
    if before_minutes <= 0 and after_minutes <= 0:
        return None

    symbol = _symbol_for_risk(signal, None)
    if not symbol:
        return None

    hours_ahead = max(1, math.ceil(max(before_minutes, 0) / 60))
    include_past_hours = max(1, math.ceil(max(after_minutes, 0) / 60))
    try:
        events = news.upcoming_events(
            symbol,
            hours_ahead=hours_ahead,
            include_past_hours=include_past_hours,
        )
    except Exception as exc:
        if bool(getattr(settings, "BLOCK_SIGNAL_ON_NEWS_FETCH_FAILURE", True)):
            return f"News blackout check unavailable for {symbol}: {exc}"
        return None

    now_aware = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
    for event in events:
        event_time = _parse_news_time(event.get("date"))
        if event_time is None:
            continue
        minutes_until = (event_time - now_aware).total_seconds() / 60.0
        if -after_minutes <= minutes_until <= before_minutes:
            title = str(event.get("title") or "scheduled news")
            impact = str(event.get("impact") or "impact")
            currency = str(event.get("currency") or "")
            return (
                f"News blackout active for {symbol}: {impact} {currency} {title} "
                f"at {event_time.isoformat()} UTC."
            )
    return None


def run_risk_checks(
    *,
    db: Session,
    user: models.User,
    account: models.BrokerAccount,
    observed_price: float,
    volume: float,
    execution_mode: str,
    quote: dict,
    signal: Optional[models.Signal] = None,
    stop_loss: Optional[float] = None,
    quote_time_str: Optional[str] = None,
    open_trade_count: int,
    daily_realized_pnl: float = 0.0,
    equity: float = 0.0,
    balance: float = 0.0,
    free_margin: float = 0.0,
    current_margin: float = 0.0,
    required_margin: float = 0.0,
    free_margin_after_trade: float = 0.0,
    effective_risk_percent: float = 0.0,
    symbol: Optional[str] = None,
    symbol_point: Optional[float] = None,
    is_jump_in: bool = False,
    now: Optional[datetime] = None,
) -> RiskCheckResult:
    """Run all final risk checks before submitting a broker order."""
    r = RiskCheckResult()
    now = now or datetime.now(UTC).replace(tzinfo=None)

    # 1. Platform controls and kill switches.
    control = trading_control.get_platform_control(db)
    if control.get("emergency_stop", False):
        r.block("Emergency stop is active. Platform trading is entirely paused.")
    if control.get("close_only_mode", False):
        r.block("Close-only mode is active. New entries are blocked.")

    if execution_mode == "live":
        kill_reason = trading_control.live_entry_block_reason(control)
        if kill_reason:
            r.block(f"Platform control: {kill_reason}")
        if not settings.ENABLE_LIVE_TRADING:
            r.block("ENABLE_LIVE_TRADING=false in platform configuration. Live trading is disabled.")
        if not user.enable_live_trading:
            r.block("User has not enabled live trading in their preferences.")
        if not user.accepted_live_disclaimer:
            r.block("User has not accepted the live trading risk disclaimer.")
    elif execution_mode == "broker_demo":
        demo_reason = trading_control.broker_demo_block_reason(control)
        if demo_reason:
            r.block(f"Platform control: {demo_reason}")

    # 2. Account validation.
    if not account.is_active:
        r.block("Broker account is inactive.")
    if not account.metaapi_account_id:
        r.block("Broker account is not connected to MetaApi.")
    if account.connection_state != "deployed":
        r.block(
            f"Broker account connection state is '{account.connection_state}'. "
            "Deploy the account before trading."
        )
    account_type = _value(account.account_type)
    if execution_mode == "live" and account_type != "live":
        r.block(
            "Selected account is a DEMO account but execution mode is LIVE. "
            "Use a verified live broker account for live orders."
        )
    if execution_mode == "broker_demo" and account_type != "demo":
        r.block(
            "Selected account is a LIVE account but execution mode is BROKER_DEMO. "
            "Use a demo broker account for demo orders to avoid real-money risk."
        )

    # 3. Quote freshness.
    if quote_time_str:
        try:
            quote_time = datetime.fromisoformat(str(quote_time_str).replace("Z", "+00:00"))
            if quote_time.tzinfo is None:
                quote_time = quote_time.replace(tzinfo=UTC)
            age = (datetime.now(UTC) - quote_time).total_seconds()
            if age > settings.QUOTE_STALE_AFTER_SECONDS:
                r.block(
                    f"Broker quote is {age:.0f}s old (limit {settings.QUOTE_STALE_AFTER_SECONDS}s). "
                    "Cannot execute on stale price."
                )
        except Exception:
            r.block("Broker quote time could not be parsed. Cannot execute without a verifiable fresh price.")

    if observed_price <= 0:
        r.block("Observed price is zero or negative.")

    # 4. Signal validity and duplicate prevention.
    if signal:
        signal_status = getattr(signal.status, "value", str(signal.status))
        if signal_status != "approved":
            r.block(f"Signal status is '{signal_status}' - only approved signals can be executed.")
        if signal.valid_until and signal.valid_until <= now:
            r.block("Signal has expired.")

        open_signal_trade = db.query(models.Trade).filter(
            models.Trade.signal_id == signal.id,
            models.Trade.status == models.TradeStatus.OPEN,
        ).first()
        if open_signal_trade:
            r.block("Signal already has an open trade. Duplicate execution is blocked.")
        if _active_signal_intent_exists(db, signal.id, execution_mode):
            r.block("Signal already has an active execution intent. Duplicate execution is blocked.")

    # 5. Stop-loss, direction, and reward:risk.
    effective_sl = stop_loss if stop_loss is not None else (signal.stop_loss if signal else None)
    if not effective_sl or effective_sl <= 0:
        r.block("Stop-loss is required for every order.")

    if signal and effective_sl and observed_price > 0:
        direction = str(signal.signal_type or "").lower()
        take_profit = float(signal.take_profit_1 or 0.0)
        if direction == "buy":
            if effective_sl >= observed_price:
                r.block("Buy stop-loss must be below the observed price.")
            if take_profit <= observed_price:
                r.block("Buy take-profit must be above the observed price.")
        elif direction == "sell":
            if effective_sl <= observed_price:
                r.block("Sell stop-loss must be above the observed price.")
            if take_profit >= observed_price:
                r.block("Sell take-profit must be below the observed price.")
        else:
            r.block("Signal direction must be buy or sell.")

    # 6. Entry price validation.
    if signal and signal.entry_min and signal.entry_max:
        if is_jump_in:
            mid_entry = (signal.entry_min + signal.entry_max) / 2
            distance_pct = abs(observed_price - mid_entry) / mid_entry if mid_entry > 0 else 0
            if distance_pct > JUMP_IN_TOLERANCE_PCT:
                r.block(
                    f"Current price {observed_price:.5f} is {distance_pct * 100:.2f}% from entry zone mid "
                    f"{mid_entry:.5f} (limit {JUMP_IN_TOLERANCE_PCT * 100:.1f}%). "
                    "Price has moved too far from the setup - jump-in blocked."
                )
        elif not (signal.entry_min <= observed_price <= signal.entry_max):
            r.block(
                f"Observed price {observed_price:.5f} is outside entry zone "
                f"{signal.entry_min:.5f}-{signal.entry_max:.5f}."
            )

    # 7. Signal quality and spread.
    if signal and signal.confidence < settings.MIN_SIGNAL_CONFIDENCE:
        r.block(
            f"Signal confidence {signal.confidence}% is below minimum {settings.MIN_SIGNAL_CONFIDENCE}%."
        )

    if signal:
        risk_reward = _risk_reward_for_signal(signal, observed_price)
        if risk_reward is None:
            r.block("Signal reward:risk could not be calculated from entry, stop-loss, and take-profit.")
        elif risk_reward < settings.MIN_SIGNAL_RISK_REWARD:
            r.block(
                f"Signal reward:risk {risk_reward:.2f}:1 is below minimum "
                f"{settings.MIN_SIGNAL_RISK_REWARD:.2f}:1."
            )

    max_spread_points = None
    if signal and getattr(signal, "scanner_profile", None):
        max_spread_points = getattr(signal.scanner_profile, "max_spread_points", None)
    if max_spread_points is None:
        configured_spread = float(getattr(settings, "MAX_BROKER_SPREAD_POINTS", 0.0) or 0.0)
        max_spread_points = configured_spread if configured_spread > 0 else None
    spread_points = _spread_points(quote, symbol_point)
    if max_spread_points is not None and spread_points is not None and spread_points > float(max_spread_points):
        r.block(
            f"Current spread {spread_points:.1f} points exceeds maximum {float(max_spread_points):.1f} points."
        )

    # 8. Open-position limits.
    if open_trade_count >= user.max_open_trades:
        r.block(
            f"Maximum open trade limit ({user.max_open_trades}) reached. "
            "Close an existing position before opening a new one."
        )

    risk_symbol = _symbol_for_risk(signal, symbol)
    max_per_symbol = int(getattr(settings, "MAX_OPEN_TRADES_PER_SYMBOL", 1) or 0)
    if max_per_symbol > 0 and execution_mode in ("live", "broker_demo"):
        open_symbol_count = _open_symbol_trade_count(
            db,
            user_id=user.id,
            broker_account_id=account.id,
            symbol=risk_symbol,
            execution_mode=execution_mode,
        )
        if open_symbol_count >= max_per_symbol:
            r.block(
                f"Maximum open-position limit for {risk_symbol or 'this symbol'} "
                f"({max_per_symbol}) reached."
            )

    # 9. Daily realized loss.
    if equity > 0 and user.max_daily_loss_percent > 0:
        daily_loss_pct = abs(daily_realized_pnl) / equity * 100 if daily_realized_pnl < 0 else 0
        if daily_loss_pct >= user.max_daily_loss_percent:
            r.block(
                f"Daily loss limit reached: {daily_loss_pct:.1f}% "
                f"(limit {user.max_daily_loss_percent:.1f}%). "
                "No new trades today."
            )

    # 10. Drawdown, news blackout, and account exposure.
    max_drawdown_percent = float(getattr(settings, "MAX_ACCOUNT_DRAWDOWN_PERCENT", 0.0) or 0.0)
    if balance > 0 and equity > 0 and max_drawdown_percent > 0:
        drawdown_percent = max(0.0, (balance - equity) / balance * 100.0)
        if drawdown_percent >= max_drawdown_percent:
            r.block(
                f"Account drawdown {drawdown_percent:.1f}% exceeds maximum "
                f"{max_drawdown_percent:.1f}%."
            )

    if signal:
        blackout_reason = _news_blackout_reason(signal, now)
        if blackout_reason:
            r.block(blackout_reason)

    max_exposure_percent = float(getattr(settings, "MAX_ACCOUNT_EXPOSURE_PERCENT", 0.0) or 0.0)
    if execution_mode in ("broker_demo", "live") and equity > 0 and max_exposure_percent > 0:
        exposure_percent = max(0.0, current_margin + required_margin) / equity * 100.0
        if exposure_percent > max_exposure_percent:
            r.block(
                f"Account margin exposure after order would be {exposure_percent:.1f}% "
                f"(limit {max_exposure_percent:.1f}%)."
            )

    # 11. Volume and per-trade live risk.
    if volume <= 0:
        r.block("Volume must be positive.")
    if volume > settings.MAX_LIVE_ORDER_VOLUME and execution_mode == "live":
        r.block(f"Volume {volume} exceeds platform maximum {settings.MAX_LIVE_ORDER_VOLUME} lots.")

    max_live_risk_percent = float(getattr(settings, "MAX_LIVE_RISK_PERCENT", 0.25))
    if execution_mode == "live" and effective_risk_percent > max_live_risk_percent:
        r.block(
            f"Live order risk {effective_risk_percent:.2f}% exceeds maximum "
            f"{max_live_risk_percent:.2f}% account risk per trade."
        )

    # 12. Broker-calculated margin.
    if execution_mode in ("broker_demo", "live"):
        if required_margin <= 0:
            r.block("Broker-side margin calculation is required before execution.")
        elif required_margin > free_margin:
            r.block(
                f"Insufficient free margin. Required margin: {required_margin:.2f}, "
                f"available: {free_margin:.2f}."
            )
        elif free_margin_after_trade < 0:
            r.block("Free margin after trade would be negative.")

    return r
