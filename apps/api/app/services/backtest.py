"""Template-based backtesting engine v1.

Maps a strategy's chosen indicators onto one of three canonical rule
templates (EMA cross, MACD cross, RSI mean-reversion), runs it over real
Deriv candles, and produces the metrics stored on the Backtest model.

Execution model: one position at a time, entry at next candle open after a
signal, ATR-based stop (1.5x) and target (2.25x, 1.5R), stop checked before
target inside a candle (conservative), opposite signal closes at open.
Position size risks strategy.risk_per_trade % of current balance.
"""

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from app.services import marketdata

ATR_PERIOD = 14
STOP_ATR = 1.5
TARGET_ATR = 2.25


@dataclass
class BacktestOutcome:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_profit: float
    profit_factor: float
    max_drawdown: float
    average_win: float
    average_loss: float
    risk_reward_ratio: float
    equity_curve: list
    trades_log: list
    template: str


class BacktestError(Exception):
    pass


def _pick_template(strategy) -> str:
    trend = [str(i).upper() for i in (strategy.trend_indicators or [])]
    momentum = [str(i).upper() for i in (strategy.momentum_indicators or [])]
    if any("EMA" in i or "SMA" in i or "MA" == i for i in trend):
        return "ema_cross"
    if any("MACD" in i for i in momentum):
        return "macd_cross"
    if any("RSI" in i for i in momentum):
        return "rsi_reversion"
    return "ema_cross"


def _signals(df: pd.DataFrame, template: str) -> pd.Series:
    """+1 buy signal, -1 sell signal, 0 nothing, evaluated on closed candles."""
    close = df["close"]
    if template == "ema_cross":
        fast = close.ewm(span=12, adjust=False).mean()
        slow = close.ewm(span=26, adjust=False).mean()
        above = fast > slow
        cross_up = above & ~above.shift(1, fill_value=False)
        cross_down = ~above & above.shift(1, fill_value=True)
        return cross_up.astype(int) - cross_down.astype(int)

    if template == "macd_cross":
        fast = close.ewm(span=12, adjust=False).mean()
        slow = close.ewm(span=26, adjust=False).mean()
        macd = fast - slow
        signal_line = macd.ewm(span=9, adjust=False).mean()
        above = macd > signal_line
        cross_up = above & ~above.shift(1, fill_value=False)
        cross_down = ~above & above.shift(1, fill_value=True)
        return cross_up.astype(int) - cross_down.astype(int)

    # rsi_reversion
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, 1e-12)
    rsi = 100 - (100 / (1 + rs))
    cross_up = (rsi > 30) & (rsi.shift(1) <= 30)
    cross_down = (rsi < 70) & (rsi.shift(1) >= 70)
    return cross_up.astype(int) - cross_down.astype(int)


def run_backtest(strategy, symbol: str, timeframe: str, start_epoch: int, end_epoch: int, initial_balance: float) -> BacktestOutcome:
    try:
        candles = marketdata.get_candles(symbol, timeframe, 5000)
    except marketdata.MarketDataError as exc:
        raise BacktestError(str(exc)) from exc

    df = pd.DataFrame(candles)
    df = df[(df["time"] >= start_epoch) & (df["time"] <= end_epoch)].reset_index(drop=True)
    if len(df) < 60:
        raise BacktestError(
            f"Only {len(df)} candles available in the selected window (the data feed keeps "
            f"the most recent 5000 {timeframe} candles). Choose a more recent date range or a larger timeframe."
        )

    template = _pick_template(strategy)
    signals = _signals(df, template)

    # ATR for stops/targets
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    true_range = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1 / ATR_PERIOD, adjust=False).mean()

    balance = initial_balance
    peak = initial_balance
    max_drawdown = 0.0
    position: Optional[dict] = None
    wins: list[float] = []
    losses: list[float] = []
    equity_curve: list[dict] = []
    trades_log: list[dict] = []
    risk_fraction = max(0.1, min(strategy.risk_per_trade or 1.0, 5.0)) / 100.0

    def close_position(exit_price: float, epoch: int, reason: str):
        nonlocal balance, peak, max_drawdown, position
        direction = 1 if position["side"] == "buy" else -1
        pnl = position["size"] * (exit_price - position["entry"]) * direction
        balance += pnl
        (wins if pnl > 0 else losses).append(pnl)
        trades_log.append({
            "side": position["side"], "entry": position["entry"], "exit": exit_price,
            "entry_time": position["entry_time"], "exit_time": epoch, "pnl": round(pnl, 2), "reason": reason,
        })
        peak = max(peak, balance)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - balance) / peak * 100)
        position = None

    for i in range(ATR_PERIOD + 1, len(df) - 1):
        epoch = int(df.at[i, "time"])

        if position:
            candle_high, candle_low = float(df.at[i, "high"]), float(df.at[i, "low"])
            if position["side"] == "buy":
                if candle_low <= position["stop"]:
                    close_position(position["stop"], epoch, "stop")
                elif candle_high >= position["target"]:
                    close_position(position["target"], epoch, "target")
            else:
                if candle_high >= position["stop"]:
                    close_position(position["stop"], epoch, "stop")
                elif candle_low <= position["target"]:
                    close_position(position["target"], epoch, "target")

        signal = int(signals.iat[i])
        if signal == 0:
            equity_curve.append({"time": epoch, "balance": round(balance, 2)})
            continue

        side = "buy" if signal > 0 else "sell"
        if position and position["side"] != side:
            close_position(float(df.at[i + 1, "open"]), epoch, "flip")
        if position is None:
            entry = float(df.at[i + 1, "open"])
            candle_atr = float(atr.iat[i])
            if candle_atr <= 0:
                continue
            stop_distance = STOP_ATR * candle_atr
            stop = entry - stop_distance if side == "buy" else entry + stop_distance
            target = entry + TARGET_ATR * candle_atr if side == "buy" else entry - TARGET_ATR * candle_atr
            size = (balance * risk_fraction) / stop_distance
            position = {
                "side": side, "entry": entry, "stop": stop, "target": target,
                "size": size, "entry_time": int(df.at[i + 1, "time"]),
            }
        equity_curve.append({"time": epoch, "balance": round(balance, 2)})

    if position:
        close_position(float(df.iloc[-1]["close"]), int(df.iloc[-1]["time"]), "end_of_data")

    total = len(wins) + len(losses)
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    return BacktestOutcome(
        total_trades=total,
        winning_trades=len(wins),
        losing_trades=len(losses),
        win_rate=round(len(wins) / total * 100, 2) if total else 0.0,
        total_profit=round(balance - initial_balance, 2),
        profit_factor=round(gross_win / gross_loss, 2) if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0),
        max_drawdown=round(max_drawdown, 2),
        average_win=round(gross_win / len(wins), 2) if wins else 0.0,
        average_loss=round(-gross_loss / len(losses), 2) if losses else 0.0,
        risk_reward_ratio=round(TARGET_ATR / STOP_ATR, 2),
        equity_curve=equity_curve[-1000:],
        trades_log=trades_log[-500:],
        template=template,
    )
