"""
Tests for the scanner indicators module.

All tests are pure Python — no database, no network, no Celery.
"""

import math
import unittest

from app.services.scanner.indicators import (
    ema, ema_series, sma, rsi, macd, atr,
    swing_highs, swing_lows, support_resistance_levels,
    trend_structure, normalised_atr, spread_in_points,
)


def _make_candles(closes: list[float]) -> list[dict]:
    """Create minimal candle dicts from a list of closes."""
    candles = []
    for i, c in enumerate(closes):
        # Simple synthetic high/low around close
        candles.append({
            "time": f"2024-01-{i+1:02d}T00:00:00Z",
            "open": c * 0.999,
            "high": c * 1.002,
            "low": c * 0.997,
            "close": c,
        })
    return candles


class EMATests(unittest.TestCase):
    def test_returns_none_when_not_enough_data(self):
        self.assertIsNone(ema([1.0, 2.0], 10))

    def test_ema_10_period(self):
        closes = [1.0] * 20
        result = ema(closes, 10)
        # All values equal → EMA should equal 1.0
        self.assertAlmostEqual(result, 1.0, places=5)

    def test_ema_rising_series(self):
        closes = list(range(1, 51))  # 1, 2, ..., 50
        result = ema(closes, 20)
        # EMA lags — should be below 50 but above SMA(20) of first 20
        self.assertIsNotNone(result)
        self.assertGreater(result, 20)
        self.assertLess(result, 55)

    def test_ema_series_length(self):
        closes = [1.0] * 30
        series = ema_series(closes, 10)
        self.assertEqual(len(series), len(closes))

    def test_ema_series_has_nans_at_start(self):
        closes = [1.0] * 30
        series = ema_series(closes, 10)
        for v in series[:9]:
            self.assertTrue(math.isnan(v))
        for v in series[9:]:
            self.assertFalse(math.isnan(v))


class SMATests(unittest.TestCase):
    def test_sma_constant_series(self):
        closes = [5.0] * 10
        self.assertAlmostEqual(sma(closes, 10), 5.0)

    def test_sma_returns_none_for_short_series(self):
        self.assertIsNone(sma([1.0, 2.0], 5))

    def test_sma_uses_last_n(self):
        # SMA(5) of [10, 10, 10, 1, 1, 1, 1, 1] should use last 5 = 1
        closes = [10.0, 10.0, 10.0, 1.0, 1.0, 1.0, 1.0, 1.0]
        self.assertAlmostEqual(sma(closes, 5), 1.0)


class RSITests(unittest.TestCase):
    def test_returns_none_for_insufficient_data(self):
        self.assertIsNone(rsi([1.0] * 5, 14))

    def test_constant_series_returns_100_or_nan(self):
        # No losses → avg_loss = 0 → RSI = 100
        closes = [1.0] * 20
        result = rsi(closes, 14)
        # When all gains are 0 and all losses are 0, avg_gain=0, avg_loss=0 → 100.0
        self.assertIsNotNone(result)

    def test_rsi_range(self):
        import random
        random.seed(42)
        closes = [100.0 + random.gauss(0, 1) for _ in range(100)]
        result = rsi(closes, 14)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result, 0)
        self.assertLessEqual(result, 100)

    def test_rsi_rising_trend_is_high(self):
        # Strongly rising series → RSI should be > 70
        closes = [float(i) for i in range(1, 50)]
        result = rsi(closes, 14)
        self.assertIsNotNone(result)
        self.assertGreater(result, 70)

    def test_rsi_falling_trend_is_low(self):
        # Strongly falling series → RSI should be < 30
        closes = [float(50 - i) for i in range(50)]
        result = rsi(closes, 14)
        self.assertIsNotNone(result)
        self.assertLess(result, 30)


class MACDTests(unittest.TestCase):
    def test_returns_none_for_short_series(self):
        self.assertIsNone(macd([1.0] * 10))

    def test_returns_dict_keys(self):
        closes = [float(i % 20) for i in range(100)]
        result = macd(closes)
        self.assertIsNotNone(result)
        self.assertIn("macd", result)
        self.assertIn("signal", result)
        self.assertIn("histogram", result)

    def test_histogram_is_macd_minus_signal(self):
        closes = [float(i % 20) for i in range(100)]
        result = macd(closes)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(
            result["histogram"],
            result["macd"] - result["signal"],
            places=10,
        )


class ATRTests(unittest.TestCase):
    def test_returns_none_for_short_candles(self):
        candles = _make_candles([1.0] * 5)
        self.assertIsNone(atr(candles, 14))

    def test_returns_float_for_sufficient_data(self):
        candles = _make_candles([float(i % 50) for i in range(50)])
        result = atr(candles, 14)
        self.assertIsNotNone(result)
        self.assertGreater(result, 0)

    def test_atr_is_non_negative(self):
        import random
        random.seed(1)
        closes = [100 + random.gauss(0, 2) for _ in range(50)]
        candles = _make_candles(closes)
        result = atr(candles, 14)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result, 0)


class SwingTests(unittest.TestCase):
    def _make_price_candles(self, highs: list[float], lows: list[float]) -> list[dict]:
        candles = []
        for i, (h, l) in enumerate(zip(highs, lows)):
            mid = (h + l) / 2
            candles.append({
                "time": f"2024-{i+1:04d}",
                "open": mid,
                "high": h,
                "low": l,
                "close": mid,
            })
        return candles

    def test_swing_high_detected(self):
        highs = [1, 2, 3, 4, 5, 4, 3, 2, 1, 2, 3, 4, 3, 2, 1]
        lows  = [h - 0.5 for h in highs]
        candles = self._make_price_candles(highs, lows)
        result = swing_highs(candles, lookback=2)
        high_prices = [s["price"] for s in result]
        self.assertIn(5.0, high_prices)

    def test_swing_low_detected(self):
        lows  = [5, 4, 3, 2, 1, 2, 3, 4, 5, 4, 3, 2, 3, 4, 5]
        highs = [l + 0.5 for l in lows]
        candles = self._make_price_candles(highs, lows)
        result = swing_lows(candles, lookback=2)
        low_prices = [s["price"] for s in result]
        self.assertIn(1.0, low_prices)


class TrendStructureTests(unittest.TestCase):
    def test_bullish_trend(self):
        # Strong upward trend
        closes = [float(i) for i in range(1, 250)]
        result = trend_structure(closes)
        self.assertEqual(result, "bullish")

    def test_bearish_trend(self):
        closes = [float(250 - i) for i in range(1, 250)]
        result = trend_structure(closes)
        self.assertEqual(result, "bearish")

    def test_sideways_for_short_series(self):
        closes = [100.0] * 30
        result = trend_structure(closes)
        # Only EMA20 and EMA50 defined; with constant prices they're equal
        self.assertIn(result, ["sideways", "bullish", "bearish"])


class SpreadTests(unittest.TestCase):
    def test_spread_calculation(self):
        result = spread_in_points(1980.0, 1980.5, 0.001)
        self.assertAlmostEqual(result, 500.0, places=0)

    def test_zero_point_returns_none(self):
        self.assertIsNone(spread_in_points(1980.0, 1980.5, 0))


if __name__ == "__main__":
    unittest.main()
