import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from app.services.risk_engine import run_risk_checks


class _Query:
    def __init__(self, db, model):
        self.db = db
        self.model = model

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        model_name = getattr(self.model, "__name__", "")
        if model_name == "Trade" and self.db.open_signal_trade:
            return SimpleNamespace(id=99)
        if model_name == "ExecutionIntent":
            return self.db.active_intent
        return None

    def count(self):
        model_name = getattr(self.model, "__name__", "")
        if model_name == "Trade":
            return self.db.open_symbol_count
        return 0


class _DB:
    def __init__(self, *, open_symbol_count=0, active_intent=None, open_signal_trade=False):
        self.open_symbol_count = open_symbol_count
        self.active_intent = active_intent
        self.open_signal_trade = open_signal_trade

    def query(self, model):
        return _Query(self, model)


def _control():
    return {
        "live_trading_allowed": True,
        "new_live_entries_allowed": True,
        "broker_demo_trading_allowed": True,
        "paper_trading_allowed": True,
        "emergency_stop": False,
        "close_only_mode": False,
    }


def _user():
    return SimpleNamespace(
        id=1,
        enable_live_trading=True,
        accepted_live_disclaimer=True,
        max_open_trades=5,
        max_daily_loss_percent=3.0,
    )


def _account():
    return SimpleNamespace(
        id=7,
        is_active=True,
        metaapi_account_id="acct-1",
        connection_state="deployed",
        account_type="live",
    )


def _signal(**overrides):
    values = {
        "id": 42,
        "status": "approved",
        "valid_until": datetime.utcnow() + timedelta(hours=1),
        "signal_type": "buy",
        "symbol": "EURUSD",
        "canonical_symbol": "EURUSD",
        "broker_symbol": "EURUSD",
        "entry_min": 1.09,
        "entry_max": 1.11,
        "stop_loss": 1.08,
        "take_profit_1": 1.14,
        "confidence": 80,
        "scanner_profile": SimpleNamespace(
            max_spread_points=None,
            news_block_before_minutes=0,
            news_block_after_minutes=0,
        ),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _run(**overrides):
    kwargs = dict(
        db=_DB(),
        user=_user(),
        account=_account(),
        observed_price=1.1002,
        volume=0.1,
        execution_mode="live",
        quote={"bid": 1.1000, "ask": 1.1002},
        signal=_signal(),
        quote_time_str=None,
        open_trade_count=0,
        daily_realized_pnl=0.0,
        equity=10000.0,
        balance=10000.0,
        free_margin=8000.0,
        current_margin=1000.0,
        required_margin=100.0,
        free_margin_after_trade=7900.0,
        effective_risk_percent=0.1,
        symbol="EURUSD",
        symbol_point=0.0001,
    )
    kwargs.update(overrides)
    with patch("app.services.risk_engine.trading_control.get_platform_control", return_value=_control()):
        return run_risk_checks(**kwargs)


class RiskEngineRegressionTests(unittest.TestCase):
    def test_signal_spread_cap_blocks_order(self):
        signal = _signal(scanner_profile=SimpleNamespace(
            max_spread_points=10.0,
            news_block_before_minutes=0,
            news_block_after_minutes=0,
        ))

        result = _run(signal=signal, quote={"bid": 1.1000, "ask": 1.1015})

        self.assertFalse(result.approved)
        self.assertTrue(any("spread" in reason.lower() for reason in result.reasons))

    def test_active_signal_intent_blocks_duplicate_execution(self):
        result = _run(db=_DB(active_intent=SimpleNamespace(id=5, status="SUBMITTING")))

        self.assertFalse(result.approved)
        self.assertTrue(any("active execution intent" in reason.lower() for reason in result.reasons))

    def test_per_symbol_position_limit_blocks_order(self):
        result = _run(db=_DB(open_symbol_count=1))

        self.assertFalse(result.approved)
        self.assertTrue(any("maximum open-position limit" in reason.lower() for reason in result.reasons))

    def test_drawdown_and_margin_exposure_block_order(self):
        result = _run(
            equity=7000.0,
            balance=10000.0,
            current_margin=6000.0,
            required_margin=1000.0,
        )

        self.assertFalse(result.approved)
        self.assertTrue(any("drawdown" in reason.lower() for reason in result.reasons))
        self.assertTrue(any("exposure" in reason.lower() for reason in result.reasons))

    @patch("app.services.risk_engine.news.upcoming_events")
    def test_news_blackout_blocks_signal_trade(self, mock_news):
        now = datetime(2026, 1, 1, 12, 0, 0)
        mock_news.return_value = [{
            "title": "Non-Farm Payrolls",
            "currency": "USD",
            "impact": "High",
            "date": "2026-01-01T12:10:00+00:00",
        }]
        signal = _signal(scanner_profile=SimpleNamespace(
            max_spread_points=None,
            news_block_before_minutes=30,
            news_block_after_minutes=30,
        ))

        result = _run(signal=signal, now=now)

        self.assertFalse(result.approved)
        self.assertTrue(any("news blackout" in reason.lower() for reason in result.reasons))


if __name__ == "__main__":
    unittest.main()
