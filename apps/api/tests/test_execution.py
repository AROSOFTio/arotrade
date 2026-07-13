import sys
import unittest
from unittest.mock import MagicMock, patch
from datetime import timedelta
from types import SimpleNamespace, ModuleType

# Setup stub config so we can import services without loading real settings
config_module = ModuleType("app.config")
config_module.settings = SimpleNamespace(
    ENABLE_LIVE_TRADING=True,
    MIN_SIGNAL_CONFIDENCE=70,
    MIN_SIGNAL_RISK_REWARD=1.5,
    REDIS_URL="redis://localhost:6379/0",
    MAX_LIVE_ORDER_VOLUME=1.0,
    MAX_LIVE_RISK_PERCENT=0.25,
    QUOTE_STALE_AFTER_SECONDS=10.0,
    PAPER_TRADING_ENABLED=True,
    DEMO_INITIAL_BALANCE=10000.0,
    APP_URL="http://localhost:3000",
    SMTP_HOST="",
)
config_module.DATABASE_URL = "sqlite:///:memory:"
sys.modules.setdefault("app.config", config_module)

from app.services.execution import evaluate_signal_for_execution, utc_now, execute_signal_trade, verify_live_broker_account
from app import models


def approved_buy_signal(**overrides):
    values = {
        "id": 1,
        "symbol": "EURUSD",
        "broker_symbol": "EURUSD",
        "status": "approved",
        "valid_until": utc_now() + timedelta(minutes=10),
        "confidence": 80,
        "entry_min": 100.0,
        "entry_max": 101.0,
        "stop_loss": 99.0,
        "take_profit_1": 103.0,
        "signal_type": "buy",
        "scanner_profile": SimpleNamespace(risk_percent=1.0)
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def active_user(**overrides):
    values = {"id": 1, "is_active": True, "max_open_trades": 2, "default_risk_percent": 1.0}
    values.update(overrides)
    return SimpleNamespace(**values)


class SignalExecutionGateTests(unittest.TestCase):
    @patch("app.services.execution.metaapi")
    def test_live_verification_accepts_rest_response_without_sync_status(self, mock_meta):
        mock_meta.get_account.return_value = {
            "id": "acct-1",
            "state": "DEPLOYED",
            "connectionStatus": "CONNECTED",
            "broker": "Exness",
            "server": "Exness-MT5",
            "login": "12345678",
        }
        mock_meta.get_account_information.return_value = {
            "tradeAllowed": True,
            "type": "ACCOUNT_TRADE_MODE_REAL",
            "currency": "USD",
        }
        account = SimpleNamespace(
            metaapi_account_id="acct-1",
            connection_state="deployed",
            broker="exness",
            server="Exness-MT5",
            account_id="12345678",
            currency="USD",
        )

        result = verify_live_broker_account(account)

        self.assertTrue(result.connected)
        self.assertTrue(result.synchronized)
        self.assertTrue(result.is_real)
        self.assertTrue(result.trade_allowed)

    def test_approved_signal_with_valid_price_is_eligible(self):
        result = evaluate_signal_for_execution(
            approved_buy_signal(), active_user(), open_trade_count=0, observed_price=100.0
        )

        self.assertTrue(result.eligible)
        self.assertEqual(result.reasons, [])
        self.assertEqual(result.calculated_risk_reward, 3.0)

    def test_signal_outside_entry_range_is_rejected(self):
        result = evaluate_signal_for_execution(
            approved_buy_signal(), active_user(), open_trade_count=0, observed_price=102.0
        )

        self.assertFalse(result.eligible)
        self.assertIn("Observed price is outside the signal entry range", result.reasons)

    def test_signal_at_open_trade_limit_is_rejected(self):
        result = evaluate_signal_for_execution(
            approved_buy_signal(), active_user(max_open_trades=1), open_trade_count=1, observed_price=100.0
        )

        self.assertFalse(result.eligible)
        self.assertIn("Maximum open-trade limit reached", result.reasons)

    @patch("app.services.execution.redis_client")
    @patch("app.services.execution.metaapi")
    @patch("app.services.execution.calculate_position_size")
    @patch("app.services.execution.run_risk_checks")
    def test_paper_execution_creates_correct_trade_record(self, mock_risk, mock_size, mock_meta, mock_redis):
        # Setup mocks
        mock_redis.lock.return_value = MagicMock()
        
        mock_meta.get_symbol_price.return_value = {"bid": 100.5, "ask": 100.5}
        mock_meta.get_symbol_specification.return_value = {"digits": 5, "volumeStep": 0.01}
        mock_meta.extract_observed_price.return_value = 100.5
        mock_meta.get_account_information.return_value = {
            "balance": 10000.0,
            "equity": 10000.0,
            "freeMargin": 10000.0,
            "margin": 0.0,
        }

        sizing_result = SimpleNamespace(
            blocked=False,
            final_volume=0.1,
            risk_amount=100.0,
            loss_per_lot=1000.0,
            stop_loss_distance=1.0,
            raw_volume=0.105
        )
        mock_size.return_value = sizing_result

        risk_result = SimpleNamespace(approved=True, reasons=[])
        mock_risk.return_value = risk_result

        # Mock DB session
        db_mock = MagicMock()
        def db_query_side_effect(model_class):
            mock_query = MagicMock()
            if model_class == models.User:
                mock_query.filter.return_value.first.return_value = active_user()
            elif model_class == models.BrokerAccount:
                mock_query.filter.return_value.first.return_value = SimpleNamespace(
                    id=1, metaapi_account_id="test-acct", is_active=True, connection_state="deployed",
                    balance=10000.0, platform="mt5", broker="Exness", account_type="demo"
                )
            elif model_class == models.Signal:
                mock_query.filter.return_value.with_for_update.return_value.first.return_value = approved_buy_signal()
            else:
                mock_query.filter.return_value.first.return_value = None
            
            mock_query.filter.return_value.count.return_value = 0
            mock_query.filter.return_value.all.return_value = []
            return mock_query

        db_mock.query.side_effect = db_query_side_effect

        trade = execute_signal_trade(
            db=db_mock,
            user_id=1,
            signal_id=1,
            broker_account_id=1,
            execution_mode="paper"
        )

        self.assertIsNotNone(trade)
        self.assertEqual(trade.execution_mode, "paper")
        self.assertEqual(trade.provider, "paper")
        self.assertEqual(trade.actual_volume, 0.1)
        self.assertEqual(trade.entry_price, 100.5)


if __name__ == "__main__":
    unittest.main()
