"""Tests for the position sizing engine."""

import unittest

from app.services.position_sizing import (
    calculate_position_size,
    SizingSpec,
    _round_down_to_step,
)


def _spec(**overrides) -> SizingSpec:
    defaults = dict(
        tick_size=0.01,
        tick_value=1.0,
        contract_size=100.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
    )
    defaults.update(overrides)
    return SizingSpec(**defaults)


class RoundDownTests(unittest.TestCase):
    def test_round_down_exact(self):
        self.assertAlmostEqual(_round_down_to_step(0.10, 0.01), 0.10)

    def test_round_down_not_round_up(self):
        # 0.1234 should become 0.12, NOT 0.13
        result = _round_down_to_step(0.1234, 0.01)
        self.assertAlmostEqual(result, 0.12, places=5)

    def test_round_down_large_step(self):
        # 0.55 lots with step 0.5 → 0.5 lots (not 1.0)
        result = _round_down_to_step(0.55, 0.5)
        self.assertAlmostEqual(result, 0.5, places=5)

    def test_zero_step_returns_original(self):
        self.assertAlmostEqual(_round_down_to_step(1.234, 0), 1.234)


class PositionSizingTests(unittest.TestCase):
    def test_basic_buy_sizing(self):
        spec = _spec(tick_size=0.01, tick_value=1.0, volume_min=0.01, volume_step=0.01)
        result = calculate_position_size(
            equity=10000.0,
            risk_percent=1.0,
            entry_price=1980.0,
            stop_loss=1975.0,  # 5-point SL = 500 ticks * $1 = $500/lot
            spec=spec,
            free_margin=5000.0,
            direction="buy",
        )
        # risk_amount = 100, sl_dist = 5, ticks = 500, loss_per_lot = 500
        # raw_volume = 100/500 = 0.20
        self.assertFalse(result.blocked)
        self.assertAlmostEqual(result.raw_volume, 0.20, places=5)
        self.assertAlmostEqual(result.final_volume, 0.20, places=5)

    def test_sell_requires_sl_above_entry(self):
        spec = _spec()
        result = calculate_position_size(
            equity=10000.0,
            risk_percent=1.0,
            entry_price=1980.0,
            stop_loss=1970.0,  # Below entry for SELL → invalid
            spec=spec,
            free_margin=5000.0,
            direction="sell",
        )
        self.assertTrue(result.blocked)
        self.assertIn("above", result.block_reason.lower())

    def test_buy_requires_sl_below_entry(self):
        spec = _spec()
        result = calculate_position_size(
            equity=10000.0,
            risk_percent=1.0,
            entry_price=1980.0,
            stop_loss=1985.0,  # Above entry for BUY → invalid
            spec=spec,
            free_margin=5000.0,
            direction="buy",
        )
        self.assertTrue(result.blocked)
        self.assertIn("below", result.block_reason.lower())

    def test_never_exceeds_risk_amount(self):
        spec = _spec(tick_size=0.01, tick_value=0.10, volume_min=0.01, volume_step=0.01)
        result = calculate_position_size(
            equity=10000.0,
            risk_percent=1.0,
            entry_price=1980.0,
            stop_loss=1975.0,
            spec=spec,
            free_margin=5000.0,
            direction="buy",
        )
        if not result.blocked:
            actual_risk = result.final_volume * result.loss_per_lot
            self.assertLessEqual(actual_risk, result.risk_amount + 0.01)

    def test_volume_below_minimum_is_blocked(self):
        spec = _spec(volume_min=1.0, volume_step=0.01)  # min is 1 lot
        result = calculate_position_size(
            equity=1000.0,
            risk_percent=1.0,  # Only $10 risk
            entry_price=1980.0,
            stop_loss=1975.0,  # 5-point SL, $10 risk → 0.02 lots — below min 1.0
            spec=spec,
            free_margin=5000.0,
            direction="buy",
        )
        self.assertTrue(result.blocked)
        self.assertIn("below", result.block_reason.lower())

    def test_missing_tick_size_blocks(self):
        spec = _spec(tick_size=0)
        result = calculate_position_size(
            equity=10000.0,
            risk_percent=1.0,
            entry_price=1980.0,
            stop_loss=1975.0,
            spec=spec,
            free_margin=5000.0,
            direction="buy",
        )
        self.assertTrue(result.blocked)
        self.assertIn("tick_size", result.block_reason.lower())

    def test_missing_tick_value_blocks(self):
        spec = _spec(tick_value=0)
        result = calculate_position_size(
            equity=10000.0,
            risk_percent=1.0,
            entry_price=1980.0,
            stop_loss=1975.0,
            spec=spec,
            free_margin=5000.0,
            direction="buy",
        )
        self.assertTrue(result.blocked)
        self.assertIn("tick_value", result.block_reason.lower())

    def test_zero_equity_blocks(self):
        spec = _spec()
        result = calculate_position_size(
            equity=0,
            risk_percent=1.0,
            entry_price=1980.0,
            stop_loss=1975.0,
            spec=spec,
            free_margin=5000.0,
            direction="buy",
        )
        self.assertTrue(result.blocked)

    def test_zero_sl_distance_blocks(self):
        spec = _spec()
        result = calculate_position_size(
            equity=10000.0,
            risk_percent=1.0,
            entry_price=1980.0,
            stop_loss=1980.0,  # Same as entry
            spec=spec,
            free_margin=5000.0,
            direction="buy",
        )
        self.assertTrue(result.blocked)

    def test_volume_capped_at_platform_max(self):
        spec = _spec(volume_max=1000.0)
        result = calculate_position_size(
            equity=10_000_000.0,  # Very large account
            risk_percent=1.0,
            entry_price=1980.0,
            stop_loss=1979.0,   # Very tight SL → large volume
            spec=spec,
            free_margin=5_000_000.0,
            direction="buy",
            platform_max_volume=10.0,  # Platform cap
        )
        if not result.blocked:
            self.assertLessEqual(result.final_volume, 10.0)

    def test_audit_dict_keys(self):
        spec = _spec()
        result = calculate_position_size(
            equity=10000.0,
            risk_percent=1.0,
            entry_price=1980.0,
            stop_loss=1975.0,
            spec=spec,
            free_margin=5000.0,
            direction="buy",
        )
        d = result.to_audit_dict()
        for key in ("final_volume", "raw_volume", "risk_amount", "equity", "risk_percent",
                    "entry_price", "stop_loss", "tick_size", "tick_value", "blocked"):
            self.assertIn(key, d)


class SizingRoundDownTests(unittest.TestCase):
    """Verify that calculated volumes are always rounded DOWN (never up)."""

    def test_round_down_for_xauusd_realistic(self):
        # XAUUSD: tick_size=0.01, tick_value=$0.01/tick/lot (simplified)
        # Using point=0.01, contract_size=100
        spec = SizingSpec(
            tick_size=0.01,
            tick_value=0.01,
            contract_size=100.0,
            volume_min=0.01,
            volume_max=50.0,
            volume_step=0.01,
        )
        result = calculate_position_size(
            equity=5000.0,
            risk_percent=1.0,
            entry_price=1980.50,
            stop_loss=1975.50,
            spec=spec,
            free_margin=3000.0,
            direction="buy",
        )
        if not result.blocked:
            # Verify volume is a multiple of step
            remainder = result.final_volume % spec.volume_step
            self.assertAlmostEqual(remainder, 0.0, places=5)

            # Verify it's rounded DOWN (never exceeds raw_volume)
            self.assertLessEqual(result.final_volume, result.raw_volume + 0.00001)


if __name__ == "__main__":
    unittest.main()
