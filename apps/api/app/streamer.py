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
except ImportError:
    # Fallback/stub for local environment testing where SDK might not be installed yet
    class SynchronizationListener:
        pass
    logger.warning("metaapi_cloud_sdk not found in this environment. Falling back to stub listener.")


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
                "bid": float(bid),
                "ask": float(ask),
                "spread": float(ask - bid),
                "time": str(broker_time),
                "cached_at": datetime.now(UTC).isoformat()
            }

            # Cache in Redis with a TTL of 30 seconds
            cache_key = f"quote:{self.local_account_id}:{symbol.upper()}"
            redis_client.set(cache_key, json.dumps(quote_data), ex=30)

            # Publish update on Redis pubsub
            redis_client.publish(f"channel:quotes:{self.local_account_id}", json.dumps(quote_data))
            
            logger.debug("Quote cached & published: %s %s: Bid %s / Ask %s", self.account_id, symbol, bid, ask)
        except Exception as exc:
            logger.error("Error in on_symbol_price_updated for %s: %s", self.account_id, exc)

    async def on_candles_updated(self, instance_index: str, candles):
        """Callback from MetaApi when candles update."""
        # Optional: cache M1/H1 candles if needed, otherwise rely on REST API
        pass


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

        # Retrieve symbols to stream
        db = SessionLocal()
        try:
            # 1. Active scanner profile symbols
            scanner_symbols = [
                sym[0] for sym in db.query(models.ScannerProfile.broker_symbol)
                .filter(models.ScannerProfile.is_active == True, models.ScannerProfile.broker_symbol.isnot(None))
                .distinct().all()
            ]
            
            # 2. Open trades symbols
            trade_symbols = [
                t[0] for t in db.query(models.Trade.broker_symbol)
                .filter(models.Trade.status == models.TradeStatus.OPEN, models.Trade.broker_symbol.isnot(None))
                .distinct().all()
            ]

            symbols_to_stream = list(set(scanner_symbols + trade_symbols))
            if not symbols_to_stream:
                # Default fallback watchlist
                symbols_to_stream = ["EURUSD", "GBPUSD", "XAUUSD", "USDJPY", "BTCUSD"]

            for symbol in symbols_to_stream:
                try:
                    logger.info("Subscribing to market data for %s: %s", metaapi_account_id, symbol)
                    await connection.subscribe_to_market_data(symbol)
                except Exception as e:
                    logger.error("Failed to subscribe to %s on %s: %s", symbol, metaapi_account_id, e)
        finally:
            db.close()

        # Keep connection alive
        while True:
            await asyncio.sleep(10)

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
        await asyncio.sleep(60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Streamer daemon stopped by user.")
