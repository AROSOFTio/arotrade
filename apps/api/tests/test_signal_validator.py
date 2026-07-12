"""Tests for the scanner signal validator."""

import unittest
from datetime import datetime, UTC, timedelta

from app.services.scanner.validator import (
    validate_signal_candidate,
    pre_screen_candidate,
    build_signal_fingerprint,
)


def _utc(offset_minutes=0):
    return datetime.now(UTC) + timedelta(minutes=offset_minutes)


class ValidateSignalCandidateTests(unittest.TestCase):

    def _valid_buy(self, **overrides):
        kwargs = dict(
            direction="buy",
            entry_min=1979.0,
            entry_max=1981.0,
            stop_loss=1974.0,
            take_profit_1=1990.0,
            confidence=75,
            risk_reward=2.0,
            current_price=1980.0,
            spread_points=3.0,
            max_spread_points=20.0,
            signal_rr_minimum=1.5,
            confidence_minimum=70,
            candle_age_seconds=60.0,
            max_candle_age_seconds=300.0,
            existing_fingerprint=False,
        )
        kwargs.update(overrides)
        return validate_signal_candidate(**kwargs)

    def _valid_sell(self, **overrides):
        kwargs = dict(
            direction="sell",
            entry_min=1979.0,
            entry_max=1981.0,
            stop_loss=1986.0,
            take_profit_1=1970.0,
            confidence=75,
            risk_reward=2.0,
            current_price=1980.0,
            spread_points=3.0,
            max_spread_points=20.0,
            signal_rr_minimum=1.5,
            confidence_minimum=70,
            candle_age_seconds=60.0,
            max_candle_age_seconds=300.0,
            existing_fingerprint=False,
        )
        kwargs.update(overrides)
        return validate_signal_candidate(**kwargs)

    def test_valid_buy_passes(self):
        result = self._valid_buy()
        self.assertTrue(result.passed, result.reasons)

    def test_valid_sell_passes(self):
        result = self._valid_sell()
        self.assertTrue(result.passed, result.reasons)

    def test_buy_sl_above_entry_fails(self):
        result = self._valid_buy(stop_loss=1985.0)  # SL above entry_min
        self.assertFalse(result.passed)
        self.assertTrue(any("stop-loss" in r.lower() or "sl" in r.lower() for r in result.reasons))

    def test_sell_sl_below_entry_fails(self):
        result = self._valid_sell(stop_loss=1970.0)  # SL below entry_max
        self.assertFalse(result.passed)
        self.assertTrue(any("stop-loss" in r.lower() or "sl" in r.lower() for r in result.reasons))

    def test_buy_tp_below_entry_fails(self):
        result = self._valid_buy(take_profit_1=1975.0)  # TP below entry_max
        self.assertFalse(result.passed)

    def test_sell_tp_above_entry_fails(self):
        result = self._valid_sell(take_profit_1=1990.0)  # TP above entry_min
        self.assertFalse(result.passed)

    def test_confidence_below_minimum_fails(self):
        result = self._valid_buy(confidence=50, confidence_minimum=70)
        self.assertFalse(result.passed)
        self.assertTrue(any("confidence" in r.lower() for r in result.reasons))

    def test_rr_below_minimum_fails(self):
        result = self._valid_buy(risk_reward=0.8, signal_rr_minimum=1.5)
        self.assertFalse(result.passed)
        self.assertTrue(any("risk" in r.lower() for r in result.reasons))

    def test_stale_candle_fails(self):
        result = self._valid_buy(candle_age_seconds=600.0, max_candle_age_seconds=300.0)
        self.assertFalse(result.passed)
        self.assertTrue(any("stale" in r.lower() or "old" in r.lower() for r in result.reasons))

    def test_excessive_spread_fails(self):
        result = self._valid_buy(spread_points=50.0, max_spread_points=20.0)
        self.assertFalse(result.passed)
        self.assertTrue(any("spread" in r.lower() for r in result.reasons))

    def test_existing_fingerprint_fails(self):
        result = self._valid_buy(existing_fingerprint=True)
        self.assertFalse(result.passed)
        self.assertTrue(any("fingerprint" in r.lower() or "duplicate" in r.lower() for r in result.reasons))

    def test_invalid_direction_fails(self):
        result = self._valid_buy(direction="hold")
        self.assertFalse(result.passed)

    def test_missing_entry_min_fails(self):
        result = self._valid_buy(entry_min=None)
        self.assertFalse(result.passed)

    def test_missing_stop_loss_fails(self):
        result = self._valid_buy(stop_loss=None)
        self.assertFalse(result.passed)

    def test_missing_take_profit_fails(self):
        result = self._valid_buy(take_profit_1=None)
        self.assertFalse(result.passed)


class PreScreenTests(unittest.TestCase):

    def test_neutral_rsi_fails_prescreen(self):
        result = pre_screen_candidate(
            trend="bullish",
            rsi_value=50.0,  # Neutral
            macd_histogram=0.5,
            atr_value=10.0,
            spread_points=5.0,
            max_spread_points=20.0,
        )
        self.assertFalse(result.passed)

    def test_extreme_spread_fails_prescreen(self):
        result = pre_screen_candidate(
            trend="bullish",
            rsi_value=30.0,
            macd_histogram=0.5,
            atr_value=10.0,
            spread_points=40.0,   # Way above max * 1.5
            max_spread_points=20.0,
        )
        self.assertFalse(result.passed)

    def test_good_setup_passes_prescreen(self):
        result = pre_screen_candidate(
            trend="bullish",
            rsi_value=35.0,   # Oversold
            macd_histogram=0.1,
            atr_value=10.0,
            spread_points=5.0,
            max_spread_points=20.0,
        )
        self.assertTrue(result.passed)


class FingerprintTests(unittest.TestCase):

    def test_identical_inputs_produce_same_fingerprint(self):
        dt = datetime(2024, 1, 1, 12, 0, 0)
        fp1 = build_signal_fingerprint(1, 2, "XAUUSDm", "H1", 3, dt, "buy")
        fp2 = build_signal_fingerprint(1, 2, "XAUUSDm", "H1", 3, dt, "buy")
        self.assertEqual(fp1, fp2)

    def test_different_direction_gives_different_fingerprint(self):
        dt = datetime(2024, 1, 1, 12, 0, 0)
        fp_buy = build_signal_fingerprint(1, 2, "XAUUSDm", "H1", 3, dt, "buy")
        fp_sell = build_signal_fingerprint(1, 2, "XAUUSDm", "H1", 3, dt, "sell")
        self.assertNotEqual(fp_buy, fp_sell)

    def test_different_candle_time_gives_different_fingerprint(self):
        dt1 = datetime(2024, 1, 1, 12, 0, 0)
        dt2 = datetime(2024, 1, 1, 13, 0, 0)  # +1 hour
        fp1 = build_signal_fingerprint(1, 2, "XAUUSDm", "H1", 3, dt1, "buy")
        fp2 = build_signal_fingerprint(1, 2, "XAUUSDm", "H1", 3, dt2, "buy")
        self.assertNotEqual(fp1, fp2)

    def test_fingerprint_length_is_64(self):
        fp = build_signal_fingerprint(1, 2, "XAUUSD", "H4", 1, None, "sell")
        self.assertEqual(len(fp), 64)

    def test_case_insensitive_symbol_and_direction(self):
        dt = datetime(2024, 1, 1, 0, 0, 0)
        fp1 = build_signal_fingerprint(1, 2, "xauusd", "h1", 3, dt, "BUY")
        fp2 = build_signal_fingerprint(1, 2, "XAUUSD", "H1", 3, dt, "buy")
        self.assertEqual(fp1, fp2)


if __name__ == "__main__":
    unittest.main()
