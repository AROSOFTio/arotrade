"""Server-side risk-based position sizing.

ALL volume calculations happen here. The frontend NEVER sends volume.

Algorithm:
  1. risk_amount = equity * risk_percent / 100
  2. loss_per_lot = (abs(entry - stop_loss) / tick_size) * loss_tick_value_per_lot
  3. raw_volume = risk_amount / loss_per_lot
  4. Round DOWN to volume_step precision
  5. Respect broker and platform volume limits
  6. Block if any required specification is missing

Never use MetaApi tickValue for live risk sizing. MetaApi's lossTickValue is
required because it is the broker-reported losing-side cash value per tick.
Margin is intentionally not estimated here; execution must use broker-side
margin calculation before submitting an order.
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


class SizingError(Exception):
    """Raised when position cannot be sized safely."""


@dataclass(init=False)
class SizingSpec:
    """Symbol specification required for position sizing."""
    tick_size: float
    loss_tick_value: float
    volume_min: float
    volume_max: float
    volume_step: float
    stops_level: float = 0.0
    bid: float = 0.0
    ask: float = 0.0

    def __init__(
        self,
        *,
        tick_size: float,
        loss_tick_value: float | None = None,
        volume_min: float,
        volume_max: float,
        volume_step: float,
        stops_level: float = 0.0,
        bid: float = 0.0,
        ask: float = 0.0,
        tick_value: float | None = None,
        contract_size: float | None = None,
    ) -> None:
        self.tick_size = tick_size
        self.loss_tick_value = float(loss_tick_value if loss_tick_value is not None else (tick_value or 0))
        self.volume_min = volume_min
        self.volume_max = volume_max
        self.volume_step = volume_step
        self.stops_level = stops_level
        self.bid = bid
        self.ask = ask

    @property
    def tick_value(self) -> float:
        """Backward-compatible alias for older audit/test callers."""
        return self.loss_tick_value

@dataclass
class SizingResult:
    """Result of a position sizing calculation."""
    final_volume: float
    raw_volume: float
    risk_amount: float
    loss_per_lot: float
    equity: float
    risk_percent: float
    entry_price: float
    stop_loss: float
    stop_loss_distance: float
    tick_size: float
    loss_tick_value: float
    volume_min: float
    volume_max: float
    volume_step: float
    stops_level: float = 0.0
    blocked: bool = False
    block_reason: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def tick_value(self) -> float:
        """Backward-compatible alias for older audit/test callers."""
        return self.loss_tick_value

    def to_audit_dict(self) -> dict:
        """Serialize for ExecutionIntent.request_payload."""
        return {
            "final_volume": self.final_volume,
            "raw_volume": self.raw_volume,
            "risk_amount": self.risk_amount,
            "loss_per_lot": self.loss_per_lot,
            "equity": self.equity,
            "risk_percent": self.risk_percent,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "stop_loss_distance": self.stop_loss_distance,
            "tick_size": self.tick_size,
            "loss_tick_value": self.loss_tick_value,
            "tick_value": self.loss_tick_value,
            "volume_min": self.volume_min,
            "volume_max": self.volume_max,
            "volume_step": self.volume_step,
            "stops_level": self.stops_level,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "warnings": self.warnings,
        }


def _round_down_to_step(volume: float, step: float) -> float:
    """Round volume DOWN to the nearest volume_step."""
    if step <= 0:
        return volume
    factor = 1.0 / step
    rounded_units = math.floor(volume * factor)
    rounded = rounded_units / factor
    step_text = f"{step:.10f}".rstrip("0")
    decimals = len(step_text.split(".", 1)[1]) if "." in step_text else 0
    rounded = round(rounded, decimals)
    if rounded > 0 and abs(rounded % step) > 1e-8 and abs(rounded - volume) < 1e-12:
        rounded = round((rounded_units - 1) / factor, decimals)
    return rounded


def calculate_position_size(
    *,
    equity: float,
    risk_percent: float,
    entry_price: float,
    stop_loss: float,
    spec: SizingSpec,
    direction: str,
    platform_max_volume: float = 100.0,
    free_margin: float | None = None,
) -> SizingResult:
    """Calculate a risk-based position size without estimating margin."""
    warnings: list[str] = []

    missing = []
    if not spec.tick_size or spec.tick_size <= 0:
        missing.append("tick_size")
    if not spec.loss_tick_value or spec.loss_tick_value <= 0:
        missing.append("loss_tick_value")
    if not spec.volume_min or spec.volume_min <= 0:
        missing.append("volume_min")
    if not spec.volume_max or spec.volume_max <= 0:
        missing.append("volume_max")
    if not spec.volume_step or spec.volume_step <= 0:
        missing.append("volume_step")

    if missing:
        reason = f"Broker symbol specification is incomplete: missing {', '.join(missing)}. Cannot size position safely."
        return SizingResult(
            final_volume=0.0,
            raw_volume=0.0,
            risk_amount=0.0,
            loss_per_lot=0.0,
            equity=equity,
            risk_percent=risk_percent,
            entry_price=entry_price,
            stop_loss=stop_loss,
            stop_loss_distance=0.0,
            tick_size=spec.tick_size,
            loss_tick_value=spec.loss_tick_value,
            volume_min=spec.volume_min,
            volume_max=spec.volume_max,
            volume_step=spec.volume_step,
            stops_level=spec.stops_level,
            blocked=True,
            block_reason=reason,
        )

    if equity <= 0:
        return _blocked_result("Account equity is zero or negative", equity, risk_percent, entry_price, stop_loss, spec)
    if risk_percent <= 0 or risk_percent > 100:
        return _blocked_result("Risk percent must be between 0 and 100", equity, risk_percent, entry_price, stop_loss, spec)

    sl_distance = abs(entry_price - stop_loss)
    if sl_distance <= 0:
        return _blocked_result("Stop-loss distance is zero - cannot size position", equity, risk_percent, entry_price, stop_loss, spec)

    direction_lower = direction.lower()
    if direction_lower == "buy" and stop_loss >= entry_price:
        return _blocked_result("Buy stop-loss must be below entry price", equity, risk_percent, entry_price, stop_loss, spec)
    if direction_lower == "sell" and stop_loss <= entry_price:
        return _blocked_result("Sell stop-loss must be above entry price", equity, risk_percent, entry_price, stop_loss, spec)
    if direction_lower not in ("buy", "sell"):
        return _blocked_result("Direction must be buy or sell", equity, risk_percent, entry_price, stop_loss, spec)

    if spec.stops_level and sl_distance < spec.stops_level:
        return _blocked_result(
            f"Stop-loss distance {sl_distance:.5f} is below broker stops level {spec.stops_level:.5f}",
            equity,
            risk_percent,
            entry_price,
            stop_loss,
            spec,
        )

    risk_amount = equity * risk_percent / 100.0
    loss_per_lot = (sl_distance / spec.tick_size) * spec.loss_tick_value

    if loss_per_lot <= 0:
        return _blocked_result(
            "Loss per lot calculation yielded zero - check tick_size and loss_tick_value",
            equity,
            risk_percent,
            entry_price,
            stop_loss,
            spec,
        )

    raw_volume = risk_amount / loss_per_lot
    volume = _round_down_to_step(raw_volume, spec.volume_step)

    if volume < spec.volume_min:
        reason = (
            f"Calculated volume {volume:.5f} lots is below the broker minimum "
            f"{spec.volume_min} lots. Reduce stop-loss distance or increase risk percent."
        )
        return SizingResult(
            final_volume=0.0,
            raw_volume=raw_volume,
            risk_amount=risk_amount,
            loss_per_lot=loss_per_lot,
            equity=equity,
            risk_percent=risk_percent,
            entry_price=entry_price,
            stop_loss=stop_loss,
            stop_loss_distance=sl_distance,
            tick_size=spec.tick_size,
            loss_tick_value=spec.loss_tick_value,
            volume_min=spec.volume_min,
            volume_max=spec.volume_max,
            volume_step=spec.volume_step,
            stops_level=spec.stops_level,
            blocked=True,
            block_reason=reason,
        )

    if volume > spec.volume_max:
        warnings.append(f"Volume capped at broker maximum {spec.volume_max} lots (calculated: {volume:.5f} lots)")
        volume = spec.volume_max

    if volume > platform_max_volume:
        warnings.append(f"Volume capped at platform maximum {platform_max_volume} lots (calculated: {volume:.5f} lots)")
        volume = platform_max_volume

    volume = _round_down_to_step(volume, spec.volume_step)

    return SizingResult(
        final_volume=volume,
        raw_volume=raw_volume,
        risk_amount=risk_amount,
        loss_per_lot=loss_per_lot,
        equity=equity,
        risk_percent=risk_percent,
        entry_price=entry_price,
        stop_loss=stop_loss,
        stop_loss_distance=sl_distance,
        tick_size=spec.tick_size,
        loss_tick_value=spec.loss_tick_value,
        volume_min=spec.volume_min,
        volume_max=spec.volume_max,
        volume_step=spec.volume_step,
        stops_level=spec.stops_level,
        blocked=False,
        warnings=warnings,
    )


def _blocked_result(
    reason: str,
    equity: float,
    risk_percent: float,
    entry_price: float,
    stop_loss: float,
    spec: SizingSpec,
) -> SizingResult:
    return SizingResult(
        final_volume=0.0,
        raw_volume=0.0,
        risk_amount=0.0,
        loss_per_lot=0.0,
        equity=equity,
        risk_percent=risk_percent,
        entry_price=entry_price,
        stop_loss=stop_loss,
        stop_loss_distance=abs(entry_price - stop_loss),
        tick_size=spec.tick_size,
        loss_tick_value=spec.loss_tick_value,
        volume_min=spec.volume_min,
        volume_max=spec.volume_max,
        volume_step=spec.volume_step,
        stops_level=spec.stops_level,
        blocked=True,
        block_reason=reason,
    )


def spec_from_broker_symbol(bs) -> Optional[SizingSpec]:
    """Build a SizingSpec from a BrokerSymbol ORM object."""
    if not bs:
        return None
    try:
        return SizingSpec(
            tick_size=float(bs.tick_size or 0),
            loss_tick_value=float(bs.tick_value or 0),
            volume_min=float(bs.volume_min or 0),
            volume_max=float(bs.volume_max or 0),
            volume_step=float(bs.volume_step or 0),
        )
    except (TypeError, ValueError):
        return None


def spec_from_metaapi_specification(spec_dict: dict, quote: dict | None = None) -> Optional[SizingSpec]:
    """Build a SizingSpec from raw MetaApi symbol specification and quote data."""
    quote = quote or {}
    try:
        return SizingSpec(
            tick_size=float(spec_dict.get("tickSize") or 0),
            loss_tick_value=float(spec_dict.get("lossTickValue") or 0),
            volume_min=float(spec_dict.get("minVolume") or 0),
            volume_max=float(spec_dict.get("maxVolume") or 0),
            volume_step=float(spec_dict.get("volumeStep") or 0),
            stops_level=float(spec_dict.get("stopsLevel") or 0),
            bid=float(quote.get("bid") or quote.get("brokerBid") or 0),
            ask=float(quote.get("ask") or quote.get("brokerAsk") or 0),
        )
    except (TypeError, ValueError):
        return None
