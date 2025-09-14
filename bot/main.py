import asyncio
import logging

from core.trading_bot import TradingBot
from handlers.command_handler import CommandHandler
from infrastructure.redis_manager import RedisManager
from infrastructure.shutdown_manager import ShutdownManager
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


class BotOrchestrator:
    """Orchestrates the trading bot components"""

    def __init__(self):
        self.shutdown_manager = ShutdownManager()
        self.redis_manager = RedisManager()
        self.trading_bot = TradingBot()
        self.command_handler = CommandHandler(self.redis_manager, self.shutdown_manager)

    async def start(self):
        """Start the trading bot system"""
        logger.info("Starting trading bot system...")

        await self.shutdown_manager.setup_signal_handlers()

        self.shutdown_manager.add_shutdown_callback(self.redis_manager.close)

        await self.redis_manager.connect(
            shutdown_event=self.shutdown_manager.shutdown_event
        )

        await self._update_initial_status()

        try:
            await self.command_handler.process_commands(self.trading_bot)
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        finally:
            await self.shutdown_manager.shutdown()
            logger.info("Bot system stopped")

    async def _update_initial_status(self):
        """Update initial status in Redis"""
        redis_conn = await self.redis_manager.get_connection()
        if redis_conn:
            try:
                status = self.trading_bot.get_status()
                await redis_conn.hset("bot_status", mapping=status)
                logger.debug("Initial status updated")
            except Exception as e:
                logger.error(f"Failed to update initial status: {e}")


async def main():
    orchestrator = BotOrchestrator()
    try:
        await orchestrator.start()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
