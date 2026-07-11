from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

from app.config import settings


@dataclass
class SignalGateResult:
    eligible: bool
    reasons: list[str]
    calculated_risk_reward: Optional[float]


@dataclass
class PaperFill:
    broker: str
    broker_order_id: str
    client_order_id: str
    fill_price: float


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def evaluate_signal_for_execution(signal, user, open_trade_count: int, observed_price: float, now: Optional[datetime] = None) -> SignalGateResult:
    """Apply deterministic safeguards before a signal can create a paper order."""
    now = now or utc_now()
    reasons: list[str] = []

    if not user.is_active:
        reasons.append("User account is inactive")
    signal_status = getattr(signal.status, "value", signal.status)
    if signal_status != "approved":
        reasons.append("Signal must be approved before execution")
    if signal.valid_until is not None and signal.valid_until <= now:
        reasons.append("Signal has expired")
    if signal.confidence < settings.MIN_SIGNAL_CONFIDENCE:
        reasons.append(f"Signal confidence is below {settings.MIN_SIGNAL_CONFIDENCE}%")
    if open_trade_count >= user.max_open_trades:
        reasons.append("Maximum open-trade limit reached")
    if not signal.entry_min <= observed_price <= signal.entry_max:
        reasons.append("Observed price is outside the signal entry range")

    risk_reward = None
    if signal.signal_type == "buy":
        if signal.stop_loss >= observed_price:
            reasons.append("Buy stop loss must be below the observed price")
        if signal.take_profit_1 is None or signal.take_profit_1 <= observed_price:
            reasons.append("Buy signal requires a take-profit above the observed price")
        elif observed_price > signal.stop_loss:
            risk_reward = (signal.take_profit_1 - observed_price) / (observed_price - signal.stop_loss)
    elif signal.signal_type == "sell":
        if signal.stop_loss <= observed_price:
            reasons.append("Sell stop loss must be above the observed price")
        if signal.take_profit_1 is None or signal.take_profit_1 >= observed_price:
            reasons.append("Sell signal requires a take-profit below the observed price")
        elif signal.stop_loss > observed_price:
            risk_reward = (observed_price - signal.take_profit_1) / (signal.stop_loss - observed_price)
    else:
        reasons.append("Signal direction must be buy or sell")

    if risk_reward is not None and risk_reward < settings.MIN_SIGNAL_RISK_REWARD:
        reasons.append(
            f"Calculated reward-to-risk is below {settings.MIN_SIGNAL_RISK_REWARD:.2f}"
        )

    return SignalGateResult(
        eligible=not reasons,
        reasons=reasons,
        calculated_risk_reward=risk_reward,
    )


class PaperBroker:
    """Explicitly simulated execution used until a broker demo adapter is verified."""

    name = "paper"

    def submit(self, observed_price: float) -> PaperFill:
        client_order_id = f"arotrade-{uuid4()}"
        return PaperFill(
            broker=self.name,
            broker_order_id=f"paper-{uuid4()}",
            client_order_id=client_order_id,
            fill_price=observed_price,
        )
