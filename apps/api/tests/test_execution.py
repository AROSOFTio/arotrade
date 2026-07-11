from datetime import timedelta
from types import SimpleNamespace
from types import ModuleType
import sys
import unittest

# The execution rules are deliberately unit-tested without the web stack.
# Container validation exercises the real Pydantic-backed configuration.
config_module = ModuleType("app.config")
config_module.settings = SimpleNamespace(
    MIN_SIGNAL_CONFIDENCE=70,
    MIN_SIGNAL_RISK_REWARD=1.5,
)
sys.modules.setdefault("app.config", config_module)

from app.services.execution import PaperBroker, evaluate_signal_for_execution, utc_now


def approved_buy_signal(**overrides):
    values = {
        "status": "approved",
        "valid_until": utc_now() + timedelta(minutes=10),
        "confidence": 80,
        "entry_min": 100.0,
        "entry_max": 101.0,
        "stop_loss": 99.0,
        "take_profit_1": 103.0,
        "signal_type": "buy",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def active_user(**overrides):
    values = {"is_active": True, "max_open_trades": 2}
    values.update(overrides)
    return SimpleNamespace(**values)


class SignalExecutionGateTests(unittest.TestCase):
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

    def test_paper_broker_generates_distinct_order_identifiers(self):
        fill = PaperBroker().submit(100.5)

        self.assertEqual(fill.broker, "paper")
        self.assertTrue(fill.broker_order_id.startswith("paper-"))
        self.assertTrue(fill.client_order_id.startswith("arotrade-"))
        self.assertEqual(fill.fill_price, 100.5)


if __name__ == "__main__":
    unittest.main()
