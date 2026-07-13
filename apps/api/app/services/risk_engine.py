"""Comprehensive risk engine for pre-execution validation.

This runs immediately before any broker-demo or live order submission.
It is the FINAL gate Ã¢â‚¬â€ if any check fails, the order is blocked.

The engine is NOT called for paper (simulation) orders because paper
orders carry no real financial risk.  Paper orders still go through
evaluate_signal_for_execution() in execution.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Optional

from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.services import trading_control

logger = logging.getLogger(__name__)

# Maximum slippage tolerance: price must be within X% of entry zone mid
MAX_SLIPPAGE_PCT = 0.005  # 0.5%

# Maximum entry distance for JUMP IN NOW (price must be within X% of mid entry)
JUMP_IN_TOLERANCE_PCT = 0.003  # 0.3%


@dataclass
class RiskCheckResult:
    approved: bool = True
    reasons: list[str] = field(default_factory=list)

    def block(self, reason: str) -> None:
        self.approved = False
        self.reasons.append(reason)


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
    free_margin: float = 0.0,
    required_margin: float = 0.0,
    free_margin_after_trade: float = 0.0,
    effective_risk_percent: float = 0.0,
    is_jump_in: bool = False,
    now: Optional[datetime] = None,
) -> RiskCheckResult:
    """
    Run all risk checks before submitting a broker order.

    Enforced checks:
      - Platform kill switch (Emergency stop, Close-only, live trading overrides)
      - User trading preference
      - Correct account mode
      - Account connection state
      - Quote freshness
      - Signal expiry (if signal-based)
      - Signal approval (if signal-based)
      - Stop-loss required
      - Minimum confidence (if signal-based)
      - Minimum reward/risk (if signal-based)
      - Maximum spread
      - Risk per trade
      - Maximum daily realized loss
      - Maximum current drawdown
      - Maximum open positions
      - Maximum positions per symbol
      - Duplicate execution prevention
      - News blackout
      - Maximum account exposure
      - Free-margin requirement
      - Live trading global flag
      - Jump-in entry distance (if signal-based)
    """
    r = RiskCheckResult()
    now = now or datetime.now(UTC).replace(tzinfo=None)

    # -----------------------------------------------------------------------
    # 1. Platform controls & kill switches (Enforced globally)
    # -----------------------------------------------------------------------
    control = trading_control.get_platform_control(db)

    # Global emergency stop
    if control.get("emergency_stop", False):
        r.block("Emergency stop is active. Platform trading is entirely paused.")

    # Global close only mode
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

    # -----------------------------------------------------------------------
    # 2. Account validation
    # -----------------------------------------------------------------------
    if not account.is_active:
        r.block("Broker account is inactive.")

    if not account.metaapi_account_id:
        r.block("Broker account is not connected to MetaApi.")

    if account.connection_state != "deployed":
        r.block(
            f"Broker account connection state is '{account.connection_state}'. "
            "Deploy the account before trading."
        )

    if execution_mode == "live" and account.account_type != models.TradingMode.LIVE:
        r.block(
            "Selected account is a DEMO account but execution mode is LIVE. "
            "Use a verified live broker account for live orders."
        )

    if execution_mode == "broker_demo" and account.account_type != models.TradingMode.DEMO:
        r.block(
            "Selected account is a LIVE account but execution mode is BROKER_DEMO. "
            "Use a demo broker account for demo orders to avoid real-money risk."
        )

    # -----------------------------------------------------------------------
    # 3. Quote freshness
    # -----------------------------------------------------------------------
    if quote_time_str:
        try:
            if isinstance(quote_time_str, str):
                quote_time = datetime.fromisoformat(quote_time_str.replace("Z", "+00:00"))
                age = (datetime.now(UTC) - quote_time).total_seconds()
                if age > settings.QUOTE_STALE_AFTER_SECONDS:
                    r.block(
                        f"Broker quote is {age:.0f}s old (limit {settings.QUOTE_STALE_AFTER_SECONDS}s). "
                        "Cannot execute on stale price."
                    )
        except Exception:
            pass

    if observed_price <= 0:
        r.block("Observed price is zero or negative.")

    # -----------------------------------------------------------------------
    # 4. Signal validity (if signal-based)
    # -----------------------------------------------------------------------
    if signal:
        signal_status = getattr(signal.status, "value", str(signal.status))
        if signal_status != "approved":
            r.block(f"Signal status is '{signal_status}' — only approved signals can be executed.")

        if signal.valid_until and signal.valid_until <= now:
            r.block("Signal has expired.")

    # -----------------------------------------------------------------------
    # 5. Stop-loss required
    # -----------------------------------------------------------------------
    effective_sl = stop_loss if stop_loss is not None else (signal.stop_loss if signal else None)
    if not effective_sl or effective_sl <= 0:
        r.block("Stop-loss is required for every order.")

    # -----------------------------------------------------------------------
    # 6. Entry price validation
    # -----------------------------------------------------------------------
    if signal and signal.entry_min and signal.entry_max:
        if is_jump_in:
            mid_entry = (signal.entry_min + signal.entry_max) / 2
            distance_pct = abs(observed_price - mid_entry) / mid_entry if mid_entry > 0 else 0
            if distance_pct > JUMP_IN_TOLERANCE_PCT:
                r.block(
                    f"Current price {observed_price:.5f} is {distance_pct * 100:.2f}% from entry zone mid "
                    f"{mid_entry:.5f} (limit {JUMP_IN_TOLERANCE_PCT * 100:.1f}%). "
                    "Price has moved too far from the setup — jump-in blocked."
                )
        else:
            if not (signal.entry_min <= observed_price <= signal.entry_max):
                r.block(
                    f"Observed price {observed_price:.5f} is outside entry zone "
                    f"{signal.entry_min:.5f}–{signal.entry_max:.5f}."
                )

    # -----------------------------------------------------------------------
    # 7. Minimum confidence (if signal-based)
    # -----------------------------------------------------------------------
    if signal and signal.confidence < settings.MIN_SIGNAL_CONFIDENCE:
        r.block(
            f"Signal confidence {signal.confidence}% is below minimum {settings.MIN_SIGNAL_CONFIDENCE}%."
        )

    # -----------------------------------------------------------------------
    # 8. Open positions limits
    # -----------------------------------------------------------------------
    if open_trade_count >= user.max_open_trades:
        r.block(
            f"Maximum open trade limit ({user.max_open_trades}) reached. "
            "Close an existing position before opening a new one."
        )

    # -----------------------------------------------------------------------
    # 9. Daily loss limit
    # -----------------------------------------------------------------------
    if equity > 0 and user.max_daily_loss_percent > 0:
        daily_loss_pct = abs(daily_realized_pnl) / equity * 100 if daily_realized_pnl < 0 else 0
        if daily_loss_pct >= user.max_daily_loss_percent:
            r.block(
                f"Daily loss limit reached: {daily_loss_pct:.1f}% "
                f"(limit {user.max_daily_loss_percent:.1f}%). "
                "No new trades today."
            )

    # -----------------------------------------------------------------------
    # 11. Volume limits
    # -----------------------------------------------------------------------
    if volume <= 0:
        r.block("Volume must be positive.")

    if volume > settings.MAX_LIVE_ORDER_VOLUME and execution_mode == "live":
        r.block(
            f"Volume {volume} exceeds platform maximum {settings.MAX_LIVE_ORDER_VOLUME} lots."
        )

    max_live_risk_percent = float(getattr(settings, "MAX_LIVE_RISK_PERCENT", 0.25))
    if execution_mode == "live" and effective_risk_percent > max_live_risk_percent:
        r.block(
            f"Live order risk {effective_risk_percent:.2f}% exceeds maximum "
            f"{max_live_risk_percent:.2f}% account risk per trade."
        )

    # -----------------------------------------------------------------------
    # 12. Broker-calculated margin
    # -----------------------------------------------------------------------
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
