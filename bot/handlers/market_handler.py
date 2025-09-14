import asyncio
import logging
import random

from infrastructure.shutdown_manager import ShutdownManager

logger = logging.getLogger(__name__)


class MarketHandler:
    def __init__(self, shutdown_manager: ShutdownManager, update_status_callback=None):
        self.shutdown_manager = shutdown_manager
        self.update_status_callback = update_status_callback

    async def handle_market_data(self, bot):
        """Handle incoming market data"""
        logger.info("Starting market data handler (simulated)")

        try:
            while bot.is_running and not self.shutdown_manager.is_shutdown_requested:
                try:
                    await asyncio.wait_for(
                        self.shutdown_manager.wait_for_shutdown(), timeout=1.0
                    )
                    break
                except asyncio.TimeoutError:
                    pass

                if bot.is_running and not self.shutdown_manager.is_shutdown_requested:
                    await self._simulate_trading_activity(bot)

        except asyncio.CancelledError:
            logger.info("Market data handler cancelled")
        except Exception as e:
            logger.error(f"Market data error: {e}")
            try:
                await asyncio.wait_for(
                    self.shutdown_manager.wait_for_shutdown(), timeout=5.0
                )
            except asyncio.TimeoutError:
                pass

        logger.info("Market data handler stopped")

    async def _simulate_trading_activity(self, bot):
        """Simulate some trading activity for demo purposes"""
        bot.update_pnl(random.uniform(-10, 10))

        # Update status after PnL change
        if self.update_status_callback:
            await self.update_status_callback(bot)

    async def process_market_data(self, data: str, bot):
        """Process market data and make trading decisions"""
        pass
