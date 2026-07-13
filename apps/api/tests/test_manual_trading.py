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
    MAX_LIVE_RISK_PERCENT=0.25,
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
    summarize_closing_deals,
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
            "lossTickValue": 1.0,
            "volumeMin": 0.01,
            "volumeMax": 100.0,
            "volumeStep": 0.01,
            "stopsLevel": 0.0001,
        }
        mock_metaapi.extract_observed_price.return_value = 1.1002
        mock_metaapi.calculate_margin.return_value = {"requiredMargin": 150.0}

        db_mock = MagicMock()
        db_mock.query().filter().first.side_effect = [
            SimpleNamespace(
                id=1,
                default_risk_percent=3.0,
                max_open_trades=5,
                max_daily_loss_percent=3.0,
                is_active=True,
                enable_live_trading=True,
                accepted_live_disclaimer=True,
            ),  # User
            SimpleNamespace(
                id=1,
                user_id=1,
                is_active=True,
                metaapi_account_id="acct1",
                account_type="live",
                currency="USD",
                connection_state="deployed",
            ),  # BrokerAccount
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
        self.assertAlmostEqual(res["effective_risk_percent"], 0.52, places=2)

    @patch("app.services.order_execution.run_risk_checks")
    @patch("app.services.order_execution.metaapi")
    @patch("app.services.order_execution.get_broker_account_metrics")
    @patch("app.services.order_execution.resolve_broker_symbol")
    def test_fixed_volume_passes_actual_effective_risk(self, mock_resolve, mock_metrics, mock_metaapi, mock_risk):
        mock_resolve.return_value = "EURUSD"
        mock_metrics.return_value = SimpleNamespace(
            equity=10000.0,
            balance=10000.0,
            free_margin=8000.0,
            margin=2000.0,
            is_simulated=False,
        )
        mock_metaapi.get_symbol_price.return_value = {"bid": 1.1000, "ask": 1.1000}
        mock_metaapi.get_symbol_specification.return_value = {
            "tickSize": 0.0001,
            "lossTickValue": 10.0,
            "volumeMin": 0.01,
            "volumeMax": 100.0,
            "volumeStep": 0.01,
            "stopsLevel": 0.0001,
        }
        mock_metaapi.extract_observed_price.return_value = 1.1000
        mock_metaapi.calculate_margin.return_value = {"requiredMargin": 150.0}
        mock_risk.return_value = SimpleNamespace(approved=True, reasons=[])

        db_mock = MagicMock()
        db_mock.query().filter().first.side_effect = [
            SimpleNamespace(id=1, default_risk_percent=3.0),
            SimpleNamespace(id=1, user_id=1, is_active=True, metaapi_account_id="acct1", account_type="live", currency="USD", connection_state="deployed"),
        ]
        db_mock.query().filter().count.return_value = 0

        preview_manual_order(
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

        self.assertAlmostEqual(mock_risk.call_args.kwargs["effective_risk_percent"], 0.5, places=5)

    @patch("app.services.order_execution.metaapi")
    @patch("app.services.order_execution.get_broker_account_metrics")
    @patch("app.services.order_execution.resolve_broker_symbol")
    def test_invalid_buy_sl_tp_direction_is_rejected(self, mock_resolve, mock_metrics, mock_metaapi):
        mock_resolve.return_value = "EURUSD"
        mock_metrics.return_value = SimpleNamespace(equity=10000.0, balance=10000.0, free_margin=8000.0, margin=2000.0, is_simulated=False)
        mock_metaapi.get_symbol_price.return_value = {"bid": 1.1000, "ask": 1.1000}
        mock_metaapi.get_symbol_specification.return_value = {
            "tickSize": 0.0001,
            "lossTickValue": 10.0,
            "volumeMin": 0.01,
            "volumeMax": 100.0,
            "volumeStep": 0.01,
            "stopsLevel": 0.0001,
        }
        mock_metaapi.extract_observed_price.return_value = 1.1000
        db_mock = MagicMock()
        db_mock.query().filter().first.side_effect = [
            SimpleNamespace(id=1),
            SimpleNamespace(id=1, user_id=1, is_active=True, metaapi_account_id="acct1", account_type="live", currency="USD", connection_state="deployed"),
        ]

        with self.assertRaises(ExecutionError) as ctx:
            preview_manual_order(
                db_mock,
                user_id=1,
                broker_account_id=1,
                symbol="EURUSD",
                direction="buy",
                stop_loss=1.1010,
                take_profit=1.0990,
                volume=0.1,
                risk_percent=None,
            )

        self.assertIn("BUY stop-loss", str(ctx.exception))

    @patch("app.services.order_execution.run_risk_checks")
    @patch("app.services.order_execution.metaapi")
    @patch("app.services.order_execution.get_broker_account_metrics")
    @patch("app.services.order_execution.resolve_broker_symbol")
    def test_fixed_volume_is_normalized_to_broker_step(self, mock_resolve, mock_metrics, mock_metaapi, mock_risk):
        mock_resolve.return_value = "EURUSD"
        mock_metrics.return_value = SimpleNamespace(equity=10000.0, balance=10000.0, free_margin=8000.0, margin=2000.0, is_simulated=False)
        mock_metaapi.get_symbol_price.return_value = {"bid": 1.1000, "ask": 1.1000}
        mock_metaapi.get_symbol_specification.return_value = {
            "tickSize": 0.0001,
            "lossTickValue": 10.0,
            "volumeMin": 0.01,
            "volumeMax": 100.0,
            "volumeStep": 0.01,
            "stopsLevel": 0.0001,
        }
        mock_metaapi.extract_observed_price.return_value = 1.1000
        mock_metaapi.calculate_margin.return_value = {"requiredMargin": 150.0}
        mock_risk.return_value = SimpleNamespace(approved=True, reasons=[])
        db_mock = MagicMock()
        db_mock.query().filter().first.side_effect = [
            SimpleNamespace(id=1, default_risk_percent=1.0),
            SimpleNamespace(id=1, user_id=1, is_active=True, metaapi_account_id="acct1", account_type="live", currency="USD", connection_state="deployed"),
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
            volume=0.105,
            risk_percent=None,
        )

        self.assertEqual(res["calculated_volume"], 0.1)

    def test_history_deal_summary_aggregates_closing_pnl(self):
        summary = summarize_closing_deals(
            [
                {"positionId": "pos-1", "entryType": "DEAL_ENTRY_OUT", "volume": 0.1, "price": 1.1050, "profit": 20.0, "commission": -1.0, "swap": -0.5},
                {"positionId": "pos-1", "entryType": "DEAL_ENTRY_OUT_BY", "volume": 0.1, "price": 1.1060, "profit": 25.0, "commission": -1.0, "swap": 0.0},
                {"positionId": "pos-1", "entryType": "DEAL_ENTRY_IN", "volume": 0.2, "price": 1.1000, "profit": 0.0},
            ],
            "pos-1",
        )

        self.assertIsNotNone(summary)
        self.assertAlmostEqual(summary.volume, 0.2)
        self.assertAlmostEqual(summary.exit_price, 1.1055)
        self.assertAlmostEqual(summary.broker_profit, 45.0)
        self.assertAlmostEqual(summary.commission, -2.0)
        self.assertAlmostEqual(summary.swap, -0.5)
        self.assertAlmostEqual(summary.profit_loss, 42.5)

    @patch("app.services.order_execution.metaapi")
    def test_reconcile_account_uses_history_deals_and_aggregates_close(self, mock_metaapi):
        account = SimpleNamespace(
            id=1,
            user_id=1,
            metaapi_account_id="acct1",
            connection_state="deployed",
        )
        trade = SimpleNamespace(
            id=10,
            broker_account_id=1,
            broker_position_id="pos-1",
            status=models.TradeStatus.OPEN,
            stop_loss=1.0950,
            take_profit=1.1100,
            actual_volume=0.2,
            volume=0.2,
            exit_price=None,
            exit_time=None,
            closed_time=None,
            broker_profit=None,
            profit_loss=None,
            commission=None,
            swap=None,
            reconciliation_status="pending",
            execution_status="filled",
        )

        class Query:
            def __init__(self, result):
                self.result = result

            def filter(self, *args, **kwargs):
                return self

            def first(self):
                return self.result

            def all(self):
                return self.result

        class DB:
            def __init__(self):
                self.added = []
                self.committed = False

            def query(self, model):
                if model == models.BrokerAccount:
                    return Query(account)
                if model == models.Trade:
                    return Query([trade])
                return Query(None)

            def add(self, obj):
                self.added.append(obj)

            def commit(self):
                self.committed = True

        mock_metaapi.get_positions.return_value = []
        mock_metaapi.get_history_deals.return_value = [
            {"positionId": "pos-1", "entryType": "DEAL_ENTRY_OUT", "volume": 0.1, "price": 1.1050, "profit": 20.0, "commission": -1.0, "swap": -0.5},
            {"positionId": "pos-1", "entryType": "DEAL_ENTRY_OUT_BY", "volume": 0.1, "price": 1.1060, "profit": 25.0, "commission": -1.0, "swap": 0.0},
        ]

        result = reconcile_account(1, 1, DB())

        self.assertEqual(result["reconciled"], 1)
        self.assertEqual(trade.status, models.TradeStatus.CLOSED)
        self.assertAlmostEqual(trade.exit_price, 1.1055)
        self.assertAlmostEqual(trade.broker_profit, 45.0)
        self.assertAlmostEqual(trade.profit_loss, 42.5)
        mock_metaapi.get_history_deals.assert_called_with("acct1")

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
