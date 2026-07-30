from types import SimpleNamespace

from app.routes import portfolio


class Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows


class DB:
    def __init__(self, accounts, trades):
        self.accounts = accounts
        self.trades = trades

    def query(self, model):
        if model.__name__ == "BrokerAccount":
            return Query(self.accounts)
        if model.__name__ == "Trade":
            return Query(self.trades)
        raise AssertionError(model)


def test_portfolio_summary_uses_live_direct_mt5_snapshot(monkeypatch):
    account = SimpleNamespace(
        id=7,
        user_id=1,
        name="Live MT5",
        broker="direct-mt5",
        account_id="134478618",
        account_type="live",
        balance=1000.0,
        currency="USD",
        connection_state="direct_connected",
        is_active=True,
    )
    trades = [
        SimpleNamespace(user_id=1, status="closed", profit_loss=50.0),
        SimpleNamespace(user_id=1, status="closed", profit_loss=-20.0),
        SimpleNamespace(user_id=1, status="open", profit_loss=None),
    ]
    monkeypatch.setattr(portfolio, "get_account_snapshot", lambda account_id: {
        "received_at": "2026-07-30T13:00:00Z",
        "positions": [
            {"symbol": "XAUUSDm", "volume": 0.02, "profit": 4.5},
            {"symbol": "EURUSD", "lots": 0.10, "unrealizedProfit": -1.25},
        ],
    })

    summary = portfolio.build_portfolio_summary(1, DB([account], trades))

    assert summary["total_balance"] == 1000.0
    assert summary["floating_pnl"] == 3.25
    assert summary["equity_estimate"] == 1003.25
    assert summary["realized_pnl"] == 30.0
    assert summary["win_rate"] == 50.0
    assert summary["live_position_count"] == 2
    assert summary["exposure_by_symbol"][0]["symbol"] == "XAUUSDM"