from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.routes import market as market_routes
from app.services.chart_analysis.engine import analyze_chart
from app.services.chart_analysis.fibonacci import detect_fibonacci
from app.services.chart_analysis.market_structure import (
    StructureEvent,
    StructureSnapshot,
    SwingPoint,
    confirmed_swing_highs,
)
from app.services.chart_analysis.models import (
    ChartAnalysisResponse,
    ChartCandle,
    DrawingSource,
    EntryZoneDrawing,
    ExplanationSummary,
    FibonacciDrawing,
    FibonacciLevel,
    IndicatorSummary,
    MarketState,
    SignalSummary,
    SignalMarkerDrawing,
    StopLossDrawing,
    SupportZoneDrawing,
    SwingHighDrawing,
    TextLabelDrawing,
)
from app.services.chart_analysis.signals import SignalPackage
from app.services.chart_analysis.serializer import analysis_cache_key, cache_analysis, get_cached_analysis
from app.services.chart_analysis.zones import detect_fair_value_gaps, detect_support_resistance_zones


BASE_TIME = datetime(2024, 1, 1, tzinfo=UTC)


def _dt(minutes: int) -> datetime:
    return BASE_TIME + timedelta(minutes=minutes)


def _candle(
    minutes: int,
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float | None = None,
) -> ChartCandle:
    return ChartCandle(
        time=_dt(minutes),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _structure(
    *,
    current_price: float = 100.0,
    atr_value: float = 1.0,
    trend: str = "range",
    bias: str = "neutral",
    structure: str = "mixed",
) -> StructureSnapshot:
    return StructureSnapshot(
        bias=bias,
        trend=trend,
        volatility="normal",
        structure=structure,
        current_price=current_price,
        atr=atr_value,
        ema20=100.0,
        ema50=100.0,
        ema200=100.0,
        rsi14=50.0,
        macd=0.0,
        macd_signal=0.0,
        macd_histogram=0.0,
        swing_highs=[],
        swing_lows=[],
        events=[],
        higher_highs=False,
        higher_lows=False,
        lower_highs=False,
        lower_lows=False,
    )


def _analysis_response(*, timeframe: str = "M15", last_candle_time: datetime | None = None) -> ChartAnalysisResponse:
    candle_time = last_candle_time or BASE_TIME
    return ChartAnalysisResponse(
        symbol="EURUSD",
        broker_symbol="EURUSD",
        timeframe=timeframe,
        generated_at=candle_time,
        last_candle_time=candle_time,
        analysis_version="1.0",
        market_state=MarketState(),
        indicators=IndicatorSummary(),
        drawings=[],
        signal=SignalSummary(action="WAIT", confidence=0, reasons=[], warnings=[]),
        explanation=ExplanationSummary(),
        warnings=[],
    )


class ChartStructureTests(unittest.TestCase):
    def test_confirmed_swing_highs_requires_right_hand_confirmation(self):
        candles = [
            _candle(0, open_=1.00, high=1.10, low=0.90, close=1.00),
            _candle(1, open_=1.10, high=1.20, low=1.00, close=1.10),
            _candle(2, open_=1.20, high=1.30, low=1.10, close=1.20),
            _candle(3, open_=1.90, high=2.00, low=1.70, close=1.85),
            _candle(4, open_=1.40, high=1.50, low=1.20, close=1.35),
            _candle(5, open_=1.30, high=1.40, low=1.10, close=1.25),
            _candle(6, open_=1.10, high=1.20, low=0.95, close=1.05),
        ]

        swings = confirmed_swing_highs(candles, lookback=2)

        self.assertEqual(len(swings), 1)
        self.assertEqual(swings[0].index, 3)
        self.assertEqual(swings[0].time, candles[3].time)
        self.assertEqual(swings[0].confirmed_at, candles[5].time)

    def test_support_resistance_clusters_nearby_swings(self):
        candles = [
            _candle(i, open_=100.0, high=100.2, low=99.8, close=100.0) for i in range(8)
        ]
        structure = _structure(current_price=100.0, atr_value=1.0)
        structure.swing_lows = [
            SwingPoint(index=1, time=_dt(1), price=99.00, kind="low", strength=1.2, confirmed_at=_dt(3)),
            SwingPoint(index=2, time=_dt(2), price=99.08, kind="low", strength=1.1, confirmed_at=_dt(4)),
            SwingPoint(index=5, time=_dt(5), price=95.00, kind="low", strength=0.8, confirmed_at=_dt(7)),
        ]

        drawings = detect_support_resistance_zones(
            symbol="EURUSD",
            timeframe="M15",
            candles=candles,
            structure=structure,
            created_at=BASE_TIME,
        )
        support_drawings = [drawing for drawing in drawings if drawing.type == "support_zone"]

        self.assertEqual(len(support_drawings), 2)
        touches = sorted(drawing.metadata["touches"] for drawing in support_drawings)
        self.assertEqual(touches, [1, 2])

    def test_fair_value_gap_becomes_filled_after_full_retrace(self):
        candles = [
            _candle(0, open_=9.8, high=10.0, low=9.5, close=9.9),
            _candle(1, open_=9.9, high=10.1, low=9.7, close=10.0),
            _candle(2, open_=10.7, high=11.0, low=10.4, close=10.8),
            _candle(3, open_=10.2, high=10.35, low=10.05, close=10.2),
            _candle(4, open_=9.8, high=10.45, low=9.9, close=10.1),
        ]

        drawings = detect_fair_value_gaps(
            symbol="EURUSD",
            timeframe="M15",
            candles=candles,
            created_at=BASE_TIME,
        )
        gap = next(drawing for drawing in drawings if drawing.type == "fair_value_gap")

        self.assertEqual(gap.state, "filled")
        self.assertFalse(gap.enabled)
        self.assertIsNotNone(gap.invalidation)
        self.assertEqual(gap.invalidation.status, "filled")

    def test_fibonacci_uses_confirmed_impulse_pair(self):
        candles = [
            _candle(i, open_=100.0 + i * 0.2, high=100.5 + i * 0.2, low=99.5 + i * 0.2, close=100.0 + i * 0.2)
            for i in range(8)
        ]
        structure = _structure(current_price=110.0, atr_value=2.0, trend="uptrend", bias="bullish", structure="bullish")
        structure.swing_lows = [
            SwingPoint(index=1, time=_dt(1), price=100.0, kind="low", strength=1.2, confirmed_at=_dt(4)),
        ]
        structure.swing_highs = [
            SwingPoint(index=4, time=_dt(4), price=110.0, kind="high", strength=1.5, confirmed_at=_dt(7)),
        ]

        drawings = detect_fibonacci(
            symbol="EURUSD",
            timeframe="M15",
            candles=candles,
            structure=structure,
            created_at=BASE_TIME,
        )

        self.assertEqual(len(drawings), 1)
        fib = drawings[0]
        self.assertEqual(fib.anchor_points[0].price, 100.0)
        self.assertEqual(fib.anchor_points[1].price, 110.0)
        self.assertEqual([level.ratio for level in fib.levels], [0.0, 0.382, 0.5, 0.618, 0.786, 1.0])


class ChartAnalysisEngineTests(unittest.TestCase):
    def test_analysis_cache_keys_invalidate_on_new_candle_time(self):
        analysis = _analysis_response(last_candle_time=BASE_TIME)
        first_time = BASE_TIME
        second_time = BASE_TIME + timedelta(minutes=15)

        cache_analysis(
            account_id=7,
            broker_symbol="EURUSD",
            timeframe="M15",
            latest_candle_time=first_time,
            count=300,
            include={"all"},
            analysis=analysis,
        )

        self.assertIsNotNone(
            get_cached_analysis(
                account_id=7,
                broker_symbol="EURUSD",
                timeframe="M15",
                latest_candle_time=first_time,
                count=300,
                include={"all"},
            )
        )
        self.assertIsNone(
            get_cached_analysis(
                account_id=7,
                broker_symbol="EURUSD",
                timeframe="M15",
                latest_candle_time=second_time,
                count=300,
                include={"all"},
            )
        )
        self.assertNotEqual(
            analysis_cache_key(
                account_id=7,
                broker_symbol="EURUSD",
                timeframe="M15",
                latest_candle_time=first_time,
                count=300,
                include={"all"},
                analysis_version="1.0",
            ),
            analysis_cache_key(
                account_id=7,
                broker_symbol="EURUSD",
                timeframe="M15",
                latest_candle_time=second_time,
                count=300,
                include={"all"},
                analysis_version="1.0",
            ),
        )

    @patch("app.services.chart_analysis.engine.derive_signal")
    @patch("app.services.chart_analysis.engine.detect_support_resistance_zones")
    @patch("app.services.chart_analysis.engine.build_structure_drawings")
    @patch("app.services.chart_analysis.engine.detect_market_structure")
    @patch("app.services.chart_analysis.engine.normalize_candles")
    def test_analyze_chart_preserves_core_drawings_when_optional_overlay_is_filtered(
        self,
        mock_normalize_candles,
        mock_detect_market_structure,
        mock_build_structure_drawings,
        mock_detect_support_resistance_zones,
        mock_derive_signal,
    ):
        normalized = [_candle(0, open_=100.0, high=100.5, low=99.5, close=100.0)]
        structure = _structure()
        base_drawings = [
            SwingHighDrawing(
                id="EURUSD:M15:swing-high:1",
                symbol="EURUSD",
                timeframe="M15",
                source=DrawingSource.DETERMINISTIC,
                confidence=80,
                label="Swing high",
                enabled=True,
                created_at=BASE_TIME,
                time_start=normalized[0].time,
                time_end=normalized[0].time,
                price_start=100.5,
                price_end=100.5,
                style={},
            )
        ]
        support_drawings = [
            SupportZoneDrawing(
                id="EURUSD:M15:support:1",
                symbol="EURUSD",
                timeframe="M15",
                source=DrawingSource.DETERMINISTIC,
                confidence=88,
                label="Support zone",
                enabled=True,
                created_at=BASE_TIME,
                time_start=normalized[0].time,
                time_end=normalized[0].time,
                price_low=99.4,
                price_high=99.8,
                style={},
                metadata={"touches": 2, "category": "support"},
            )
        ]
        trade_drawings = [
            EntryZoneDrawing(
                id="EURUSD:M15:entry-zone:1",
                symbol="EURUSD",
                timeframe="M15",
                source=DrawingSource.DETERMINISTIC,
                confidence=90,
                label="Entry zone",
                enabled=True,
                created_at=BASE_TIME,
                time_start=normalized[0].time,
                time_end=normalized[0].time,
                price_low=99.7,
                price_high=100.1,
                style={},
            ),
            StopLossDrawing(
                id="EURUSD:M15:stop-loss:1",
                symbol="EURUSD",
                timeframe="M15",
                source=DrawingSource.DETERMINISTIC,
                confidence=90,
                label="Stop loss",
                enabled=True,
                created_at=BASE_TIME,
                time_start=normalized[0].time,
                time_end=normalized[0].time,
                price_start=99.0,
                price_end=99.0,
                style={},
            ),
        ]
        mock_signal_package = SignalPackage(
            signal=SignalSummary(action="BUY", confidence=82, reasons=["Confluence"], warnings=[]),
            drawings=trade_drawings,
        )

        mock_normalize_candles.return_value = normalized
        mock_detect_market_structure.return_value = structure
        mock_build_structure_drawings.return_value = base_drawings
        mock_detect_support_resistance_zones.return_value = support_drawings
        mock_derive_signal.return_value = mock_signal_package

        result = analyze_chart(
            symbol="EURUSD",
            broker_symbol="EURUSD",
            timeframe="M15",
            candles=[{"time": BASE_TIME.isoformat(), "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0}],
            include="support_resistance",
            generated_at=BASE_TIME + timedelta(minutes=30),
        )

        self.assertEqual([drawing.type for drawing in result.drawings], ["swing_high", "support_zone", "entry_zone", "stop_loss"])

    def test_analysis_route_normalizes_timeframe_before_caching(self):
        account = SimpleNamespace(id=7, metaapi_account_id="acct-7")
        analysis = _analysis_response(timeframe="M15", last_candle_time=BASE_TIME)
        candle = {
            "time": BASE_TIME.isoformat(),
            "open": 100.0,
            "high": 100.5,
            "low": 99.5,
            "close": 100.0,
        }

        with (
            patch.object(market_routes, "_get_user_account", return_value=account),
            patch.object(market_routes, "_ensure_deployed_account", return_value={"state": "deployed"}),
            patch.object(market_routes, "_resolve_analysis_symbol", return_value=("EURUSD", "EURUSD")),
            patch.object(market_routes.metaapi, "normalize_timeframe", return_value="15m") as mock_normalize_timeframe,
            patch.object(market_routes.metaapi, "get_candles", return_value=[candle]) as mock_get_candles,
            patch.object(market_routes.chart_analysis_engine, "get_cached_analysis", return_value=None) as mock_get_cached,
            patch.object(market_routes.chart_analysis_engine, "analyze_chart", return_value=analysis) as mock_analyze_chart,
            patch.object(market_routes.chart_analysis_engine, "cache_analysis", return_value="cache-key") as mock_cache_analysis,
            patch.object(market_routes.chart_analysis_engine, "publish_analysis_event") as mock_publish_event,
        ):
            result = asyncio.run(
                market_routes.get_symbol_analysis(
                    account_id=7,
                    broker_symbol="EURUSD",
                    timeframe="m15",
                    count=300,
                    include="all",
                    force_refresh=False,
                    current_user={"user_id": 1},
                    db=MagicMock(),
                )
            )

        self.assertEqual(result.timeframe, "M15")
        mock_normalize_timeframe.assert_called_once_with("M15")
        mock_get_candles.assert_called_once_with("acct-7", "EURUSD", "15m", 300)
        self.assertEqual(mock_get_cached.call_args.kwargs["timeframe"], "M15")
        self.assertEqual(mock_analyze_chart.call_args.kwargs["timeframe"], "M15")
        self.assertEqual(mock_cache_analysis.call_args.kwargs["timeframe"], "M15")
        mock_publish_event.assert_called_once()


if __name__ == "__main__":
    unittest.main()
