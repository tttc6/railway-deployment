import asyncio
import logging
import os
import signal
from datetime import datetime, timezone
from typing import Any, Dict

import redis.asyncio as redis

# Configure logging
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

# Global shutdown event for graceful termination
shutdown_event = asyncio.Event()


def handle_signal(signum: int) -> None:
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_event.set()


async def setup_signal_handlers() -> None:
    """Set up asyncio signal handlers for graceful shutdown"""
    loop = asyncio.get_running_loop()

    for sig in [signal.SIGTERM, signal.SIGINT]:
        loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))

    # SIGHUP is not available on Windows, so handle it conditionally
    if hasattr(signal, "SIGHUP"):
        loop.add_signal_handler(signal.SIGHUP, lambda: handle_signal(signal.SIGHUP))


class TradingBot:
    def __init__(self):
        self.running = False
        self.positions = {}
        self.pnl = 0.0
        self.redis = None
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

    async def connect_redis(self, max_retries: int = 5):
        """Initialize async Redis connection with retry logic"""
        retry_delay = 1
        for attempt in range(max_retries):
            if shutdown_event.is_set():
                logger.info("Shutdown requested, stopping Redis connection attempts")
                return

            try:
                self.redis = redis.from_url(self.redis_url, decode_responses=True)
                await self.redis.ping()
                logger.info(f"Connected to Redis at {self.redis_url}")
                return
            except redis.ConnectionError as e:
                self.redis = None
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Failed to connect to Redis "
                        f"(attempt {attempt + 1}/{max_retries}): {e}. "
                        f"Retrying in {retry_delay} seconds..."
                    )
                    try:
                        await asyncio.wait_for(
                            shutdown_event.wait(), timeout=retry_delay
                        )
                        return  # Shutdown requested during wait
                    except asyncio.TimeoutError:
                        # Exponential backoff, max 30s
                        retry_delay = min(retry_delay * 2, 30)
                        continue
                else:
                    logger.error(
                        f"Failed to connect to Redis after {max_retries} attempts: {e}"
                    )

    async def ensure_redis_connection(self):
        """Ensure Redis connection is available, reconnect if needed"""
        if not self.redis:
            await self.connect_redis()

        if self.redis:
            try:
                await self.redis.ping()
            except redis.ConnectionError:
                logger.warning("Redis connection lost, attempting to reconnect...")
                self.redis = None
                await self.connect_redis()

    async def process_commands(self):
        """Process commands from the API via Redis"""
        market_data_task = None

        # Keep processing commands until shutdown is requested
        while not shutdown_event.is_set():
            # Ensure we have a Redis connection
            await self.ensure_redis_connection()

            if not self.redis:
                try:
                    # Check for shutdown every second while waiting for Redis
                    await asyncio.wait_for(shutdown_event.wait(), timeout=1.0)
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    continue  # Redis still not available, keep trying

            try:
                # Create a task for the Redis command to make it cancellable
                redis_task = asyncio.create_task(
                    self.redis.brpop("bot_commands", timeout=0)  # Block indefinitely
                )
                shutdown_task = asyncio.create_task(shutdown_event.wait())

                # Wait for either a Redis command or shutdown signal
                done, pending = await asyncio.wait(
                    [redis_task, shutdown_task], return_when=asyncio.FIRST_COMPLETED
                )

                # Cancel any pending tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                # Check if shutdown was requested
                if shutdown_event.is_set():
                    if not redis_task.done():
                        redis_task.cancel()
                    break

                # Process the Redis command if available
                if redis_task in done:
                    command = await redis_task
                    if command:
                        cmd = (
                            command[1]
                            if isinstance(command[1], str)
                            else command[1].decode()
                        )
                        logger.info(f"Received command: {cmd}")

                        if cmd == "START":
                            if not self.running:
                                self.running = True
                                logger.info("Bot started")
                            # Start market data handler if not already running
                            if market_data_task is None or market_data_task.done():
                                market_data_task = asyncio.create_task(
                                    self.market_data_handler()
                                )
                            await self.update_status()
                        elif cmd == "STOP":
                            logger.info("Bot stopping...")
                            self.running = False
                            # Cancel market data handler if running
                            if market_data_task and not market_data_task.done():
                                market_data_task.cancel()
                                try:
                                    await market_data_task
                                except asyncio.CancelledError:
                                    pass
                            await self.update_status()

            except redis.RedisError as e:
                logger.error(f"Redis command error: {e}")
                try:
                    # Wait before retrying, but also check for shutdown
                    await asyncio.wait_for(shutdown_event.wait(), timeout=5.0)
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    continue  # Retry after delay
            except Exception as e:
                logger.error(f"Unexpected command error: {e}")
                try:
                    # Short delay before retrying, but also check for shutdown
                    await asyncio.wait_for(shutdown_event.wait(), timeout=1.0)
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    continue  # Retry after delay

        # Clean up market data handler on shutdown
        if market_data_task and not market_data_task.done():
            logger.info("Cancelling market data handler...")
            market_data_task.cancel()
            try:
                await market_data_task
            except asyncio.CancelledError:
                pass

    async def update_status(self):
        """Update bot status in Redis"""
        if not self.redis:
            return

        try:
            status = {
                "running": str(self.running),
                "pnl": str(self.pnl),
                "positions": str(len(self.positions)),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await self.redis.hset("bot_status", mapping=status)
            logger.debug(f"Status updated: {status}")
        except redis.RedisError as e:
            logger.error(f"Failed to update status: {e}")

    async def market_data_handler(self):
        """Handle incoming market data"""
        # For now, this is a placeholder that simulates market data
        # In a real implementation, you would connect to a real market data feed
        logger.info("Starting market data handler (simulated)")

        while self.running and not shutdown_event.is_set():
            try:
                # Simulate processing market data with cancellable sleep
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=1.0)
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    pass  # Continue with normal processing

                # Simulate some trading activity
                if self.running and not shutdown_event.is_set():
                    # Update PnL randomly for demo purposes
                    import random

                    self.pnl += random.uniform(-10, 10)
                    await self.update_status()

            except asyncio.CancelledError:
                logger.info("Market data handler cancelled")
                break
            except Exception as e:
                logger.error(f"Market data error: {e}")
                try:
                    # Wait before retrying, but also check for shutdown
                    await asyncio.wait_for(shutdown_event.wait(), timeout=5.0)
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    continue  # Retry after delay

        logger.info("Market data handler stopped")

    async def process_market_data(self, data: str):
        """Process market data and make trading decisions"""
        # Placeholder for trading logic
        pass

    async def execute_trade(self, trade_data: Dict[str, Any]):
        """Execute trades via broker API"""
        # Placeholder for trade execution
        logger.info(f"Executing trade: {trade_data}")

    async def start(self):
        """Main entry point"""
        logger.info("Starting trading bot listener...")

        # Set up signal handlers
        await setup_signal_handlers()

        # Connect to Redis first
        await self.connect_redis()

        self.running = False
        await self.update_status()

        # Start the command processor which runs indefinitely
        # The market data handler is started/stopped based on running state
        try:
            await self.process_commands()
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
            shutdown_event.set()
        finally:
            logger.info("Shutting down bot...")
            self.running = False
            await self.update_status()
            if self.redis:
                await self.redis.aclose()
            logger.info("Bot stopped")


async def main():
    bot = TradingBot()
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        shutdown_event.set()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        shutdown_event.set()
    finally:
        # Ensure clean shutdown
        bot.running = False


if __name__ == "__main__":
    asyncio.run(main())
