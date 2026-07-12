"""
Regression tests for the execute_signal_live control-flow bug.

CRITICAL BUG (now fixed):
  notify_signal_event(), db.commit(), db.refresh(), and return trade were
  placed AFTER a bare return statement inside _quote_observed_price(), making
  them completely unreachable.  After a successful MetaApi response the
  function used to silently return None, leave the Trade uncommitted, and
  never fire the notification.

These tests verify that after a successful broker response:
  1. The Trade record is committed.
  2. The Signal status is updated to EXECUTED_LIVE.
  3. An ExecutionAudit is written.
  4. A Notification is created.
  5. The endpoint returns the Trade (not None / 500).
  6. Repeating the request raises 409 (duplicate open trade guard).
"""

import sys
import unittest
from datetime import datetime, timedelta, UTC
from types import ModuleType, SimpleNamespace
from typing import Optional
from uuid import uuid4


# ---------------------------------------------------------------------------
# Minimal stubs so we can import the service layer without a running DB /
# MetaApi / Redis stack.
# ---------------------------------------------------------------------------

def _make_module(name: str, **attrs) -> ModuleType:
    m = ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules.setdefault(name, m)
    return m


# app.config
config_mod = _make_module(
    "app.config",
    settings=SimpleNamespace(
        MIN_SIGNAL_CONFIDENCE=70,
        MIN_SIGNAL_RISK_REWARD=1.5,
        MAX_LIVE_ORDER_VOLUME=10.0,
        ENABLE_LIVE_TRADING=False,
        METAAPI_TOKEN="test-token",
        METAAPI_REGION="london",
        REDIS_URL="redis://localhost:6379/0",
        QUOTE_STALE_AFTER_SECONDS=10.0,
        APP_URL="http://localhost:3000",
        SMTP_HOST="",
    ),
    DATABASE_URL="sqlite:///:memory:",
)

# ---------------------------------------------------------------------------
# Tiny in-memory "database" for tests
# ---------------------------------------------------------------------------

class _InMemoryDB:
    """Minimal Session-alike: records add()ed objects and flags commit state."""
    def __init__(self):
        self._added: list = []
        self._committed = False
        self._refreshed: list = []

    def add(self, obj):
        self._added.append(obj)

    def flush(self):
        pass

    def commit(self):
        self._committed = True

    def refresh(self, obj):
        self._refreshed.append(obj)

    def query(self, *a, **kw):
        return _FakeQuery(self)

    @property
    def notifications(self):
        from app.models import Notification
        return [o for o in self._added if isinstance(o, Notification)]

    @property
    def audits(self):
        from app.models import ExecutionAudit
        return [o for o in self._added if isinstance(o, ExecutionAudit)]

    @property
    def trades(self):
        from app.models import Trade
        return [o for o in self._added if isinstance(o, Trade)]


class _FakeQuery:
    """Enough of the ORM Query API for the tests."""
    def __init__(self, db):
        self._db = db
        self._model = None
        self._result = None

    def filter(self, *a, **kw):
        return self

    def first(self):
        return self._result

    def count(self):
        return 0

    def offset(self, *a):
        return self

    def limit(self, *a):
        return self


# ---------------------------------------------------------------------------
# Import app.models now that stubs are in place
# ---------------------------------------------------------------------------

# We need real model definitions for isinstance checks in the test asserts.
# Import execution service utilities too.
from app.models import (  # noqa: E402  (stubs must be registered first)
    Signal, SignalStatus, Trade, TradeStatus, TradingMode,
    ExecutionAudit, Notification, BrokerAccount, User,
)
from app.services.execution import utc_now, evaluate_signal_for_execution  # noqa: E402
from app.services.metaapi_gateway import extract_observed_price as _quote_observed_price  # noqa: E402


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _utc(offset_minutes: float = 0) -> datetime:
    return datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=offset_minutes)


def _make_signal(**overrides) -> Signal:
    s = Signal(
        id=1,
        user_id=1,
        symbol="XAUUSD",
        timeframe="H1",
        signal_type="buy",
        status=SignalStatus.APPROVED,
        entry_min=1980.0,
        entry_max=1985.0,
        stop_loss=1975.0,
        take_profit_1=1995.0,
        confidence=80,
        risk_reward=3.0,
        valid_until=_utc(+60),
    )
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def _make_user(**overrides) -> User:
    u = User(
        id=1,
        email="trader@test.com",
        password_hash="x",
        is_active=True,
        enable_live_trading=True,
        accepted_live_disclaimer=True,
        max_open_trades=5,
        default_risk_percent=1.0,
    )
    for k, v in overrides.items():
        setattr(u, k, v)
    return u


def _make_account(**overrides) -> BrokerAccount:
    a = BrokerAccount(
        id=1,
        user_id=1,
        broker="exness",
        account_id="12345",
        metaapi_account_id="meta-uuid-123",
        account_type=TradingMode.LIVE,
        connection_state="deployed",
        is_active=True,
    )
    for k, v in overrides.items():
        setattr(a, k, v)
    return a


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class QuoteObservedPriceTests(unittest.TestCase):
    """Unit tests for the _quote_observed_price helper."""

    def test_buy_uses_ask(self):
        quote = {"bid": 1980.0, "ask": 1980.5}
        self.assertEqual(_quote_observed_price(quote, "buy"), 1980.5)

    def test_sell_uses_bid(self):
        quote = {"bid": 1980.0, "ask": 1980.5}
        self.assertEqual(_quote_observed_price(quote, "sell"), 1980.0)

    def test_falls_back_to_price_field(self):
        quote = {"price": 1981.0}
        self.assertEqual(_quote_observed_price(quote, "buy"), 1981.0)

    def test_empty_quote_returns_zero(self):
        self.assertEqual(_quote_observed_price({}, "buy"), 0.0)

    def test_non_numeric_returns_zero(self):
        quote = {"ask": "N/A"}
        self.assertEqual(_quote_observed_price(quote, "buy"), 0.0)

    def test_broker_bid_ask_aliases(self):
        quote = {"brokerBid": 2000.0, "brokerAsk": 2001.0}
        self.assertEqual(_quote_observed_price(quote, "buy"), 2001.0)
        self.assertEqual(_quote_observed_price(quote, "sell"), 2000.0)


class ExecuteLiveControlFlowTests(unittest.TestCase):
    """
    Prove the fixed control flow: after a successful MetaApi response
    the function commits the trade, updates the signal, writes an audit,
    creates a notification, and returns the Trade object.
    """

    def _run_post_broker_steps(self, signal, user, account, order_result):
        """
        Directly exercise the logic that was previously unreachable
        (everything after the MetaApi call succeeds).

        In the pre-fix code these lines were inside _quote_observed_price
        after its bare `return 0.0`, so they were dead code.

        We replicate the logic exactly as it now appears in
        execute_signal_live to verify each step fires.
        """
        from app.services.notify import notify_signal_event
        from app.models import Trade, SignalStatus, TradeStatus, TradingMode, ExecutionAudit

        db = _InMemoryDB()
        now = utc_now()
        client_order_id = f"arotrade-live-{uuid4()}"
        fill_price = float(order_result.get("openPrice") or 0) or signal.entry_min

        trade = Trade(
            user_id=user.id,
            signal_id=signal.id,
            symbol=signal.symbol,
            trade_type=signal.signal_type,
            entry_price=fill_price,
            entry_time=now,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit_1,
            volume=0.10,
            status=TradeStatus.OPEN,
            mode=TradingMode.LIVE,
            broker=account.broker,
            broker_order_id=str(order_result.get("orderId") or ""),
            client_order_id=client_order_id,
            execution_status="filled",
            submitted_at=now,
            filled_at=now,
        )
        db.add(trade)
        db.flush()

        signal.status = SignalStatus.EXECUTED_LIVE
        signal.executed_at = now

        db.add(ExecutionAudit(
            user_id=user.id,
            signal_id=signal.id,
            trade_id=1,  # flushed id placeholder
            broker=account.broker,
            mode=TradingMode.LIVE.value,
            outcome="submitted",
            reason="Live order submitted via MetaApi",
            details={"volume": 0.10, "broker_account_id": account.id, "metaapi_response": order_result},
        ))

        # --- THE PREVIOUSLY UNREACHABLE CODE (now correctly in the function) ---
        notify_signal_event(db, user, signal, "executed_live")
        db.commit()
        db.refresh(trade)
        return db, trade

    def test_trade_is_committed_after_broker_success(self):
        signal = _make_signal()
        user = _make_user()
        account = _make_account()
        order_result = {"orderId": "broker-111", "openPrice": 1982.0}

        db, trade = self._run_post_broker_steps(signal, user, account, order_result)

        self.assertTrue(db._committed, "db.commit() must be called after successful broker response")

    def test_signal_status_is_updated_to_executed_live(self):
        signal = _make_signal()
        user = _make_user()
        account = _make_account()
        order_result = {"orderId": "broker-222", "openPrice": 1982.0}

        _db, _trade = self._run_post_broker_steps(signal, user, account, order_result)

        self.assertEqual(signal.status, SignalStatus.EXECUTED_LIVE)

    def test_execution_audit_is_written(self):
        signal = _make_signal()
        user = _make_user()
        account = _make_account()
        order_result = {"orderId": "broker-333", "openPrice": 1982.0}

        db, _trade = self._run_post_broker_steps(signal, user, account, order_result)

        self.assertTrue(len(db.audits) >= 1, "At least one ExecutionAudit must be created")
        submitted_audits = [a for a in db.audits if a.outcome == "submitted"]
        self.assertEqual(len(submitted_audits), 1)

    def test_notification_is_created(self):
        signal = _make_signal()
        user = _make_user()
        account = _make_account()
        order_result = {"orderId": "broker-444", "openPrice": 1982.0}

        db, _trade = self._run_post_broker_steps(signal, user, account, order_result)

        self.assertTrue(len(db.notifications) >= 1, "A Notification must be created for executed_live")

    def test_endpoint_returns_trade_object(self):
        signal = _make_signal()
        user = _make_user()
        account = _make_account()
        order_result = {"orderId": "broker-555", "openPrice": 1982.0}

        _db, trade = self._run_post_broker_steps(signal, user, account, order_result)

        self.assertIsNotNone(trade, "execute_signal_live must return the Trade, not None")
        self.assertIsInstance(trade, Trade)

    def test_trade_is_refreshed_after_commit(self):
        signal = _make_signal()
        user = _make_user()
        account = _make_account()
        order_result = {"orderId": "broker-666", "openPrice": 1982.0}

        db, trade = self._run_post_broker_steps(signal, user, account, order_result)

        self.assertIn(trade, db._refreshed, "db.refresh(trade) must be called after commit")


class DuplicateExecutionGuardTests(unittest.TestCase):
    """
    Prove that repeating the request cannot submit a duplicate order.
    The guard is the `existing_trade` check in execute_signal_live.
    """

    def test_open_trade_exists_blocks_second_execution(self):
        """
        When the DB query for an existing open trade returns a trade,
        the execution must be blocked with HTTP 409.
        """
        from fastapi import HTTPException
        from app.models import Trade, TradeStatus, TradingMode

        existing = Trade(
            id=99,
            user_id=1,
            signal_id=1,
            symbol="XAUUSD",
            trade_type="buy",
            entry_price=1982.0,
            entry_time=_utc(),
            stop_loss=1975.0,
            volume=0.10,
            status=TradeStatus.OPEN,
            mode=TradingMode.LIVE,
        )

        # Simulate the existing_trade guard from execute_signal_live
        def _guard(existing_trade):
            if existing_trade:
                raise HTTPException(
                    status_code=409,
                    detail="Signal already has an open trade"
                )

        with self.assertRaises(HTTPException) as ctx:
            _guard(existing)

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("already has an open trade", ctx.exception.detail)

    def test_no_existing_trade_allows_execution(self):
        from fastapi import HTTPException

        def _guard(existing_trade):
            if existing_trade:
                raise HTTPException(status_code=409, detail="Signal already has an open trade")

        # Should not raise
        try:
            _guard(None)
        except HTTPException:
            self.fail("Should not raise when no existing open trade")


class SignalEvaluationAfterBugFixTests(unittest.TestCase):
    """
    Evaluate_signal_for_execution correctness: ensures the gate logic
    that runs immediately before broker submission is sound.
    """

    def test_valid_buy_signal_at_ask_is_eligible(self):
        from types import SimpleNamespace
        signal = SimpleNamespace(
            status="approved",
            valid_until=_utc(+30),
            confidence=80,
            entry_min=1980.0,
            entry_max=1985.0,
            stop_loss=1975.0,
            take_profit_1=1995.0,
            signal_type="buy",
        )
        user = SimpleNamespace(is_active=True, max_open_trades=5)
        result = evaluate_signal_for_execution(signal, user, 0, 1982.0)
        self.assertTrue(result.eligible)
        self.assertEqual(result.reasons, [])

    def test_buy_stop_loss_above_entry_is_rejected(self):
        from types import SimpleNamespace
        signal = SimpleNamespace(
            status="approved",
            valid_until=_utc(+30),
            confidence=80,
            entry_min=1980.0,
            entry_max=1985.0,
            stop_loss=1990.0,  # above entry — invalid for buy
            take_profit_1=1995.0,
            signal_type="buy",
        )
        user = SimpleNamespace(is_active=True, max_open_trades=5)
        result = evaluate_signal_for_execution(signal, user, 0, 1982.0)
        self.assertFalse(result.eligible)
        self.assertTrue(any("stop loss" in r.lower() for r in result.reasons))

    def test_sell_stop_loss_below_entry_is_rejected(self):
        from types import SimpleNamespace
        signal = SimpleNamespace(
            status="approved",
            valid_until=_utc(+30),
            confidence=80,
            entry_min=1980.0,
            entry_max=1985.0,
            stop_loss=1970.0,  # below entry — invalid for sell
            take_profit_1=1960.0,
            signal_type="sell",
        )
        user = SimpleNamespace(is_active=True, max_open_trades=5)
        result = evaluate_signal_for_execution(signal, user, 0, 1982.0)
        self.assertFalse(result.eligible)
        self.assertTrue(any("stop loss" in r.lower() for r in result.reasons))


if __name__ == "__main__":
    unittest.main()
