import asyncio
import logging
import json
import redis
from datetime import datetime, UTC
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.database import SessionLocal

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("market-streamer")

redis_client = redis.Redis.from_url(settings.REDIS_URL)

try:
    from metaapi_cloud_sdk import MetaApi
    from metaapi_cloud_sdk.clients.metaapi.synchronization_listener import SynchronizationListener
except ImportError as exc:
    raise RuntimeError("metaapi_cloud_sdk is required for the production market streamer.") from exc


def _enum_value(value):
    return getattr(value, "value", value)


class MarketDataListener(SynchronizationListener):
    def __init__(self, account_id: str, local_account_id: int):
        super().__init__()
        self.account_id = account_id
        self.local_account_id = local_account_id

    async def on_symbol_price_updated(self, instance_index: str, price):
        """Callback from MetaApi when a symbol quote updates."""
        try:
            symbol = price.get("symbol")
            bid = price.get("bid")
            ask = price.get("ask")
            broker_time = price.get("time") or datetime.now(UTC).isoformat()

            if not symbol or bid is None or ask is None:
                return

            quote_data = {
                "symbol": symbol,
                "broker_account_id": self.local_account_id,
                "exact_broker_symbol": symbol,
                "bid": float(bid),
                "ask": float(ask),
                "spread": float(ask - bid),
                "time": str(broker_time),
                "cached_at": datetime.now(UTC).isoformat()
            }

            # Cache in Redis with a TTL of 30 seconds
            cache_key = f"mt5:quote:{self.local_account_id}:{symbol.upper()}"
            redis_client.set(cache_key, json.dumps(quote_data), ex=30)

            # Record streamer heartbeat and quote latest timestamp
            redis_client.set("streamer:heartbeat", datetime.now(UTC).isoformat())
            redis_client.set("quote:latest:timestamp", datetime.now(UTC).isoformat())

            # Publish update on Redis pubsub
            redis_client.publish(f"channel:quotes:{self.local_account_id}", json.dumps(quote_data))
            
            logger.debug("Quote cached & published: %s %s: Bid %s / Ask %s", self.account_id, symbol, bid, ask)
        except Exception as exc:
            logger.error("Error in on_symbol_price_updated for %s: %s", self.account_id, exc)

    async def on_candles_updated(self, instance_index: str, candles):
        """Callback from MetaApi when candles update."""
        try:
            if isinstance(candles, dict):
                candidate = candles.get("candles") or candles.get("data") or candles.get("items") or candles
                if isinstance(candidate, list):
                    candle = candidate[-1] if candidate else None
                else:
                    candle = candidate
            elif isinstance(candles, list):
                candle = candles[-1] if candles else None
            else:
                candle = None

            if not isinstance(candle, dict):
                return

            symbol = str(candle.get("symbol") or candle.get("brokerSymbol") or candle.get("broker_symbol") or "").upper()
            time_value = candle.get("time") or candle.get("brokerTime") or candle.get("broker_time")
            if not symbol or time_value is None:
                return

            candle_data = {
                "symbol": symbol,
                "broker_account_id": self.local_account_id,
                "time": str(time_value),
                "open": float(candle.get("open") or candle.get("openPrice") or 0.0),
                "high": float(candle.get("high") or candle.get("highPrice") or 0.0),
                "low": float(candle.get("low") or candle.get("lowPrice") or 0.0),
                "close": float(candle.get("close") or candle.get("closePrice") or 0.0),
                "volume": float(candle.get("volume") or 0.0) if candle.get("volume") is not None else None,
                "cached_at": datetime.now(UTC).isoformat(),
            }

            redis_client.set(
                f"mt5:candle:{self.local_account_id}:{symbol}",
                json.dumps(candle_data),
                ex=120,
            )
            redis_client.publish(f"channel:candles:{self.local_account_id}", json.dumps(candle_data))
        except Exception as exc:
            logger.error("Error in on_candles_updated for %s: %s", self.account_id, exc)


def resolve_symbols_to_stream(db: Session, local_account: models.BrokerAccount) -> set[str]:
    """
    Resolve exact broker symbols that need streaming for this account.

    Sources:
      - Enabled scanner profiles for the account
      - Approved signals waiting for entry
      - Open broker-demo/live trades
    """
    local_id = local_account.id
    broker_symbols: set[str] = set()
    canonical_symbols: set[str] = set()

    profiles = db.query(models.ScannerProfile).filter(
        models.ScannerProfile.broker_account_id == local_id,
        models.ScannerProfile.scan_enabled == True,  # noqa: E712
    ).all()
    for profile in profiles:
        for symbol in profile.symbols or []:
            if symbol:
                canonical_symbols.add(str(symbol).upper())

    approved_signals = db.query(models.Signal).filter(
        models.Signal.broker_account_id == local_id,
        models.Signal.status == models.SignalStatus.APPROVED,
    ).all()
    for signal in approved_signals:
        if signal.broker_symbol:
            broker_symbols.add(signal.broker_symbol)
        elif signal.canonical_symbol or signal.symbol:
            canonical_symbols.add(str(signal.canonical_symbol or signal.symbol).upper())

    open_trades = db.query(models.Trade).filter(
        models.Trade.broker_account_id == local_id,
        models.Trade.status == models.TradeStatus.OPEN,
        models.Trade.execution_mode.in_([
            models.ExecutionMode.BROKER_DEMO.value,
            models.ExecutionMode.LIVE.value,
        ]),
    ).all()
    for trade in open_trades:
        if trade.broker_symbol:
            broker_symbols.add(trade.broker_symbol)

    if canonical_symbols:
        rows = db.query(models.BrokerSymbol).filter(
            models.BrokerSymbol.broker_account_id == local_id,
            models.BrokerSymbol.canonical_symbol.in_(canonical_symbols),
            models.BrokerSymbol.trade_allowed == True,  # noqa: E712
        ).all()
        resolved = {row.canonical_symbol for row in rows}
        broker_symbols.update(row.broker_symbol for row in rows if row.broker_symbol)
        unresolved = canonical_symbols - resolved
        for symbol in sorted(unresolved):
            logger.warning(
                "Streamer cannot resolve exact broker symbol for %s on account %s",
                symbol,
                local_id,
            )

    return broker_symbols


async def stream_for_account(api: MetaApi, local_account: models.BrokerAccount):
    metaapi_account_id = local_account.metaapi_account_id
    local_id = local_account.id
    logger.info("Starting streaming connection for account %s (DB ID %d)", metaapi_account_id, local_id)

    try:
        account = await api.metatrader_account_api.get_account(metaapi_account_id)
        
        # Wait for deployment if deployed/deploying
        if account.state != 'DEPLOYED':
            logger.warning("Account %s state is %s, waiting for DEPLOYED", metaapi_account_id, account.state)
            await account.wait_deployed()

        connection = account.get_streaming_connection()
        listener = MarketDataListener(metaapi_account_id, local_id)
        connection.add_synchronization_listener(listener)
        
        await connection.connect()
        await connection.wait_synchronized()
        logger.info("Streaming connection synchronized for account %s", metaapi_account_id)

        subscribed_symbols: set[str] = set()
        while True:
            db = SessionLocal()
            try:
                symbols_to_stream = resolve_symbols_to_stream(db, local_account)
            finally:
                db.close()

            if not symbols_to_stream:
                logger.info(
                    "Streamer idle for account %s: no enabled scanner profiles, approved signals, or open broker trades",
                    metaapi_account_id,
                )
            for symbol in sorted(symbols_to_stream - subscribed_symbols):
                try:
                    logger.info("Subscribing to market data for %s: %s", metaapi_account_id, symbol)
                    await connection.subscribe_to_market_data(symbol)
                    subscribed_symbols.add(symbol)
                except Exception as e:
                    logger.error("Failed to subscribe to %s on %s: %s", symbol, metaapi_account_id, e)

            redis_client.set("streamer:heartbeat", datetime.now(UTC).isoformat())
            await asyncio.sleep(60)

    except Exception as exc:
        logger.error("Streaming connection error for account %s: %s", metaapi_account_id, exc)


async def main():
    logger.info("Starting AroTrader Market Streamer Daemon")
    if not settings.METAAPI_TOKEN:
        logger.error("METAAPI_TOKEN is not set. Exiting.")
        return

    api = MetaApi(settings.METAAPI_TOKEN)
    tasks = []

    # Refresh connection loop
    while True:
        db = SessionLocal()
        try:
            # Get deployed and active accounts
            active_accounts = db.query(models.BrokerAccount).filter(
                models.BrokerAccount.is_active == True,
                models.BrokerAccount.connection_state == "deployed",
                models.BrokerAccount.metaapi_account_id.isnot(None)
            ).all()

            current_metaapi_ids = {acct.metaapi_account_id for acct in active_accounts}
            
            # Start task for any new accounts
            # (In a production code, we would compare with running tasks and clean them up if they become inactive)
            for acct in active_accounts:
                # simple one-shot task creation for this demo/setup
                if acct.metaapi_account_id not in [t.get_name() for t in tasks if not t.done()]:
                    task = asyncio.create_task(stream_for_account(api, acct), name=acct.metaapi_account_id)
                    tasks.append(task)
                    
        except Exception as exc:
            logger.error("Main loop database error: %s", exc)
        finally:
            db.close()

        # Periodically check account list every 60 seconds
        redis_client.set("streamer:heartbeat", datetime.now(UTC).isoformat())
        await asyncio.sleep(60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Streamer daemon stopped by user.")
