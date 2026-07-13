import sys
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, UTC, timedelta
from types import SimpleNamespace, ModuleType

# Setup stub config so we can import services without loading real settings
config_module = ModuleType("app.config")
config_module.settings = SimpleNamespace(
    ENABLE_LIVE_TRADING=True,
    MIN_SIGNAL_CONFIDENCE=70,
    MIN_SIGNAL_RISK_REWARD=1.5,
    REDIS_URL="redis://localhost:6379/0",
    MAX_LIVE_ORDER_VOLUME=1.0,
    QUOTE_STALE_AFTER_SECONDS=10.0,
    PAPER_TRADING_ENABLED=True,
    DEMO_INITIAL_BALANCE=10000.0,
    APP_URL="http://localhost:3000",
    SMTP_HOST="",
)
config_module.DATABASE_URL = "sqlite:///:memory:"
sys.modules.setdefault("app.config", config_module)

from app import models
from app.services.order_execution import (
    preview_manual_order,
    execute_manual_order,
    reconcile_account,
    ExecutionError,
)


class ManualTradingTests(unittest.TestCase):
    @patch("app.services.order_execution.metaapi")
    @patch("app.services.order_execution.get_broker_account_metrics")
    @patch("app.services.order_execution.resolve_broker_symbol")
    def test_preview_manual_order_fixed_volume(self, mock_resolve, mock_metrics, mock_metaapi):
        mock_resolve.return_value = "EURUSD"
        mock_metrics.return_value = SimpleNamespace(
            equity=10000.0,
            balance=10000.0,
            free_margin=8000.0,
            margin=2000.0,
            is_simulated=False,
        )
        mock_metaapi.get_symbol_price.return_value = {
            "bid": 1.1000,
            "ask": 1.1002,
            "time": datetime.utcnow().isoformat() + "Z",
        }
        mock_metaapi.get_symbol_specification.return_value = {
            "digits": 5,
            "point": 0.00001,
            "tickSize": 0.00001,
            "tickValue": 1.0,
        }
        mock_metaapi.extract_observed_price.return_value = 1.1002
        mock_metaapi.calculate_margin.return_value = {"requiredMargin": 150.0}

        db_mock = MagicMock()
        db_mock.query().filter().first.side_effect = [
            SimpleNamespace(id=1, default_risk_percent=1.0),  # User
            SimpleNamespace(id=1, user_id=1, is_active=True, metaapi_account_id="acct1", account_type="live", currency="USD"),  # BrokerAccount
            SimpleNamespace(id=1, key="platform:control", value={"live_trading_allowed": True}),  # AdminSetting
        ]
        db_mock.query().filter().count.return_value = 0

        res = preview_manual_order(
            db_mock,
            user_id=1,
            broker_account_id=1,
            symbol="EURUSD",
            direction="buy",
            stop_loss=1.0950,
            take_profit=1.1100,
            volume=0.1,
            risk_percent=None,
        )

        self.assertEqual(res["broker_symbol"], "EURUSD")
        self.assertEqual(res["direction"], "buy")
        self.assertEqual(res["calculated_volume"], 0.1)
        self.assertEqual(res["required_margin"], 150.0)
        self.assertEqual(res["free_margin_after"], 7850.0)
        self.assertFalse(res["stale_data_warning"])

    @patch("app.services.order_execution.redis_client")
    @patch("app.services.order_execution.metaapi")
    @patch("app.services.order_execution.get_broker_account_metrics")
    @patch("app.services.order_execution.resolve_broker_symbol")
    def test_execute_manual_order_idempotency(self, mock_resolve, mock_metrics, mock_metaapi, mock_redis):
        # Setup lock mock
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = True
        mock_redis.lock.return_value = mock_lock

        # Create dummy user, account
        user = models.User(id=1, default_risk_percent=1.0, is_active=True, enable_live_trading=True, accepted_live_disclaimer=True)
        account = models.BrokerAccount(id=1, user_id=1, is_active=True, metaapi_account_id="acct1", account_type="live", currency="USD")
        
        db_mock = MagicMock()
        
        # Test case 1: Intent already exists and trade filled (returns existing trade)
        existing_intent = models.ExecutionIntent(id=99, status="FILLED")
        existing_trade = models.Trade(id=101, entry_price=1.1000, volume=0.1)
        
        db_mock.query().filter().first.side_effect = [
            existing_intent,
            existing_trade,
        ]

        trade = execute_manual_order(
            db_mock,
            user_id=1,
            broker_account_id=1,
            symbol="EURUSD",
            direction="buy",
            stop_loss=1.0950,
            take_profit=1.1100,
            volume=0.1,
            risk_percent=None,
            idempotency_key="idemp_key_1",
        )
        self.assertEqual(trade.id, 101)
