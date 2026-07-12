import unittest
from types import ModuleType, SimpleNamespace
import sys

sqlalchemy_module = ModuleType("sqlalchemy")
sqlalchemy_orm_module = ModuleType("sqlalchemy.orm")
sqlalchemy_orm_module.Session = object
sys.modules.setdefault("sqlalchemy", sqlalchemy_module)
sys.modules.setdefault("sqlalchemy.orm", sqlalchemy_orm_module)

models_module = ModuleType("app.models")
models_module.AdminSetting = object
models_module.User = object
models_module.BrokerAccount = object
models_module.Trade = object
models_module.AuditLog = object
models_module.TradingMode = SimpleNamespace(LIVE="live", DEMO="demo")
models_module.TradeStatus = SimpleNamespace(OPEN="open")
sys.modules.setdefault("app.models", models_module)

config_module = ModuleType("app.config")
config_module.settings = SimpleNamespace(
    REDIS_URL="redis://localhost:6379/0",
    PAPER_TRADING_ENABLED=True,
    METAAPI_TOKEN="",
)
sys.modules.setdefault("app.config", config_module)

from app.services import trading_control


class TradingControlTests(unittest.TestCase):
    def test_live_entry_allowed_when_owner_controls_are_open(self):
        control = {
            "live_trading_allowed": True,
            "new_live_entries_allowed": True,
        }

        self.assertIsNone(trading_control.live_entry_block_reason(control))

    def test_live_entry_paused_preserves_user_preference_message(self):
        control = {
            "live_trading_allowed": False,
            "new_live_entries_allowed": True,
        }

        reason = trading_control.live_entry_block_reason(control)

        self.assertIn("Platform owner", reason)
        self.assertIn("preference remains saved", reason)

    def test_new_entries_pause_keeps_position_management_available(self):
        control = {
            "live_trading_allowed": True,
            "new_live_entries_allowed": False,
        }

        reason = trading_control.live_entry_block_reason(control)

        self.assertIn("new live entries", reason)
        self.assertIn("position management remains available", reason)


if __name__ == "__main__":
    unittest.main()
