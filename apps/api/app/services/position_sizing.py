"""Server-side risk-based position sizing.

ALL volume calculations happen here. The frontend NEVER sends volume.

Algorithm:
  1. risk_amount = equity × risk_percent / 100
  2. loss_per_lot = (abs(entry - stop_loss) / tick_size) × tick_value_per_lot
  3. raw_volume = risk_amount / loss_per_lot
  4. Round DOWN to volume_step precision
  5. Clamp to [volume_min, volume_max]
  6. Check free margin adequacy
  7. Block if any required specification is missing

Every input and result is recorded in an audit dict for the ExecutionIntent.
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


class SizingError(Exception):
    """Raised when position cannot be sized safely."""


@dataclass
class SizingSpec:
    """Symbol specification required for position sizing."""
    tick_size: float        # Minimum price movement
    tick_value: float       # P&L in account currency per lot per tick_size move
    contract_size: float    # Contract size in base currency per lot
    volume_min: float       # Minimum allowed volume
    volume_max: float       # Maximum allowed volume
    volume_step: float      # Volume granularity (round down to this)


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
    tick_value: float
    volume_min: float
    volume_max: float
    volume_step: float
    free_margin: float
    estimated_margin_used: float
    margin_ratio: float        # estimated_margin_used / free_margin
    blocked: bool = False
    block_reason: str = ""
    warnings: list[str] = field(default_factory=list)

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
            "tick_value": self.tick_value,
            "volume_min": self.volume_min,
            "volume_max": self.volume_max,
            "volume_step": self.volume_step,
            "free_margin": self.free_margin,
            "estimated_margin_used": self.estimated_margin_used,
            "margin_ratio": self.margin_ratio,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "warnings": self.warnings,
        }


def _round_down_to_step(volume: float, step: float) -> float:
    """Round volume DOWN to the nearest volume_step.

    Rounding down is critical — we must NEVER exceed the configured risk
    by rounding up.
    """
    if step <= 0:
        return volume
    factor = 1.0 / step
    return math.floor(volume * factor) / factor


def calculate_position_size(
    *,
    equity: float,
    risk_percent: float,
    entry_price: float,
    stop_loss: float,
    spec: SizingSpec,
    free_margin: float,
    direction: str,
    platform_max_volume: float = 100.0,
    margin_rate: float = 0.01,       # Estimated margin rate (1% for 100:1 leverage)
) -> SizingResult:
    """
    Calculate a risk-based position size.

    Parameters
    ----------
    equity          : Current account equity in account currency
    risk_percent    : Risk as % of equity (e.g. 1.0 = 1%)
    entry_price     : Intended entry price (ask for buy, bid for sell)
    stop_loss       : Stop-loss price
    spec            : Symbol specification from broker
    free_margin     : Available free margin in account currency
    direction       : 'buy' or 'sell'
    platform_max_volume : Platform-level safety cap (from settings)
    margin_rate     : Estimated margin rate; used for margin check only

    Returns
    -------
    SizingResult — always returned; check .blocked before using .final_volume
    """
    warnings: list[str] = []

    # -----------------------------------------------------------------------
    # 1. Validate spec fields
    # -----------------------------------------------------------------------
    missing = []
    if not spec.tick_size or spec.tick_size <= 0:
        missing.append("tick_size")
    if not spec.tick_value or spec.tick_value <= 0:
        missing.append("tick_value")
    if not spec.volume_min or spec.volume_min <= 0:
        missing.append("volume_min")
    if not spec.volume_max or spec.volume_max <= 0:
        missing.append("volume_max")
    if not spec.volume_step or spec.volume_step <= 0:
        missing.append("volume_step")

    if missing:
        reason = f"Broker symbol specification is incomplete: missing {', '.join(missing)}. Cannot size position safely."
        return SizingResult(
            final_volume=0.0, raw_volume=0.0,
            risk_amount=0.0, loss_per_lot=0.0,
            equity=equity, risk_percent=risk_percent,
            entry_price=entry_price, stop_loss=stop_loss,
            stop_loss_distance=0.0, tick_size=spec.tick_size,
            tick_value=spec.tick_value, volume_min=spec.volume_min,
            volume_max=spec.volume_max, volume_step=spec.volume_step,
            free_margin=free_margin, estimated_margin_used=0.0, margin_ratio=0.0,
            blocked=True, block_reason=reason,
        )

    # -----------------------------------------------------------------------
    # 2. Validate inputs
    # -----------------------------------------------------------------------
    if equity <= 0:
        return _blocked_result("Account equity is zero or negative", equity, risk_percent,
                               entry_price, stop_loss, spec, free_margin)
    if risk_percent <= 0 or risk_percent > 100:
        return _blocked_result("Risk percent must be between 0 and 100", equity, risk_percent,
                               entry_price, stop_loss, spec, free_margin)

    sl_distance = abs(entry_price - stop_loss)
    if sl_distance <= 0:
        return _blocked_result("Stop-loss distance is zero — cannot size position", equity, risk_percent,
                               entry_price, stop_loss, spec, free_margin)

    # Direction sanity
    if direction.lower() == "buy" and stop_loss >= entry_price:
        return _blocked_result("Buy stop-loss must be below entry price", equity, risk_percent,
                               entry_price, stop_loss, spec, free_margin)
    if direction.lower() == "sell" and stop_loss <= entry_price:
        return _blocked_result("Sell stop-loss must be above entry price", equity, risk_percent,
                               entry_price, stop_loss, spec, free_margin)

    # -----------------------------------------------------------------------
    # 3. Core calculation
    # -----------------------------------------------------------------------
    risk_amount = equity * risk_percent / 100.0

    # Number of ticks in the stop-loss distance
    ticks_in_sl = sl_distance / spec.tick_size

    # Loss in account currency if 1 lot moves sl_distance against us
    loss_per_lot = ticks_in_sl * spec.tick_value

    if loss_per_lot <= 0:
        return _blocked_result(
            "Loss per lot calculation yielded zero — check tick_size and tick_value",
            equity, risk_percent, entry_price, stop_loss, spec, free_margin,
        )

    raw_volume = risk_amount / loss_per_lot

    # -----------------------------------------------------------------------
    # 4. Round DOWN to volume_step
    # -----------------------------------------------------------------------
    volume = _round_down_to_step(raw_volume, spec.volume_step)

    # -----------------------------------------------------------------------
    # 5. Apply limits
    # -----------------------------------------------------------------------
    if volume < spec.volume_min:
        reason = (
            f"Calculated volume {volume:.5f} lots is below the broker minimum "
            f"{spec.volume_min} lots. Reduce stop-loss distance or increase risk percent."
        )
        return SizingResult(
            final_volume=0.0, raw_volume=raw_volume,
            risk_amount=risk_amount, loss_per_lot=loss_per_lot,
            equity=equity, risk_percent=risk_percent,
            entry_price=entry_price, stop_loss=stop_loss,
            stop_loss_distance=sl_distance, tick_size=spec.tick_size,
            tick_value=spec.tick_value, volume_min=spec.volume_min,
            volume_max=spec.volume_max, volume_step=spec.volume_step,
            free_margin=free_margin, estimated_margin_used=0.0, margin_ratio=0.0,
            blocked=True, block_reason=reason,
        )

    if volume > spec.volume_max:
        warnings.append(
            f"Volume capped at broker maximum {spec.volume_max} lots "
            f"(calculated: {volume:.5f} lots)"
        )
        volume = spec.volume_max

    if volume > platform_max_volume:
        warnings.append(
            f"Volume capped at platform maximum {platform_max_volume} lots "
            f"(calculated: {volume:.5f} lots)"
        )
        volume = platform_max_volume

    # -----------------------------------------------------------------------
    # 6. Margin check
    # -----------------------------------------------------------------------
    estimated_margin = (volume * spec.contract_size * entry_price * margin_rate
                        if spec.contract_size else volume * entry_price * margin_rate)
    margin_ratio = estimated_margin / free_margin if free_margin > 0 else float("inf")

    if margin_ratio > 0.8:
        reason = (
            f"Estimated margin {estimated_margin:.2f} would use "
            f"{margin_ratio * 100:.0f}% of free margin ({free_margin:.2f}). "
            "Execution blocked to protect account."
        )
        return SizingResult(
            final_volume=0.0, raw_volume=raw_volume,
            risk_amount=risk_amount, loss_per_lot=loss_per_lot,
            equity=equity, risk_percent=risk_percent,
            entry_price=entry_price, stop_loss=stop_loss,
            stop_loss_distance=sl_distance, tick_size=spec.tick_size,
            tick_value=spec.tick_value, volume_min=spec.volume_min,
            volume_max=spec.volume_max, volume_step=spec.volume_step,
            free_margin=free_margin, estimated_margin_used=estimated_margin,
            margin_ratio=margin_ratio,
            blocked=True, block_reason=reason,
        )

    # -----------------------------------------------------------------------
    # 7. Final round-down (in case caps introduced precision issues)
    # -----------------------------------------------------------------------
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
        tick_value=spec.tick_value,
        volume_min=spec.volume_min,
        volume_max=spec.volume_max,
        volume_step=spec.volume_step,
        free_margin=free_margin,
        estimated_margin_used=estimated_margin,
        margin_ratio=margin_ratio,
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
    free_margin: float,
) -> SizingResult:
    return SizingResult(
        final_volume=0.0, raw_volume=0.0,
        risk_amount=0.0, loss_per_lot=0.0,
        equity=equity, risk_percent=risk_percent,
        entry_price=entry_price, stop_loss=stop_loss,
        stop_loss_distance=abs(entry_price - stop_loss),
        tick_size=spec.tick_size, tick_value=spec.tick_value,
        volume_min=spec.volume_min, volume_max=spec.volume_max,
        volume_step=spec.volume_step,
        free_margin=free_margin, estimated_margin_used=0.0, margin_ratio=0.0,
        blocked=True, block_reason=reason,
    )


def spec_from_broker_symbol(bs) -> Optional[SizingSpec]:
    """
    Build a SizingSpec from a BrokerSymbol ORM object.
    Returns None if critical fields are missing.
    """
    if not bs:
        return None
    try:
        return SizingSpec(
            tick_size=float(bs.tick_size or 0),
            tick_value=float(bs.tick_value or 0),
            contract_size=float(bs.contract_size or 0),
            volume_min=float(bs.volume_min or 0),
            volume_max=float(bs.volume_max or 0),
            volume_step=float(bs.volume_step or 0),
        )
    except (TypeError, ValueError):
        return None


def spec_from_metaapi_specification(spec_dict: dict) -> Optional[SizingSpec]:
    """
    Build a SizingSpec from a raw MetaApi symbol specification dict.
    """
    try:
        return SizingSpec(
            tick_size=float(spec_dict.get("tickSize") or 0),
            tick_value=float(spec_dict.get("tickValue") or 0),
            contract_size=float(spec_dict.get("contractSize") or 0),
            volume_min=float(spec_dict.get("minVolume") or 0),
            volume_max=float(spec_dict.get("maxVolume") or 0),
            volume_step=float(spec_dict.get("volumeStep") or 0),
        )
    except (TypeError, ValueError):
        return None
