import asyncio
import logging
from typing import Optional

import redis.asyncio as redis
from infrastructure.redis_manager import RedisManager
from infrastructure.shutdown_manager import ShutdownManager

logger = logging.getLogger(__name__)


class CommandHandler:
    def __init__(self, redis_manager: RedisManager, shutdown_manager: ShutdownManager):
        self.redis_manager = redis_manager
        self.shutdown_manager = shutdown_manager
        self._market_data_task: Optional[asyncio.Task] = None

    async def process_commands(self, bot):
        """Process commands from the API via Redis"""
        while not self.shutdown_manager.is_shutdown_requested:
            redis_conn = await self.redis_manager.get_connection()

            if not redis_conn:
                try:
                    await asyncio.wait_for(
                        self.shutdown_manager.wait_for_shutdown(), timeout=1.0
                    )
                    break
                except asyncio.TimeoutError:
                    continue

            try:
                redis_task = asyncio.create_task(
                    redis_conn.brpop("bot_commands", timeout=0)
                )
                self.shutdown_manager.register_task(redis_task)

                shutdown_task = asyncio.create_task(
                    self.shutdown_manager.wait_for_shutdown()
                )

                done, pending = await asyncio.wait(
                    [redis_task, shutdown_task], return_when=asyncio.FIRST_COMPLETED
                )

                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                if shutdown_task in done:
                    logger.info("Command processing cancelled due to shutdown")
                    break

                if redis_task in done:
                    command = await redis_task
                    if command:
                        cmd = (
                            command[1]
                            if isinstance(command[1], str)
                            else command[1].decode()
                        )
                        logger.info(f"Received command: {cmd}")
                        await self._handle_command(cmd, bot)

            except redis.RedisError as e:
                logger.error(f"Redis command error: {e}")
                try:
                    await asyncio.wait_for(
                        self.shutdown_manager.wait_for_shutdown(), timeout=5.0
                    )
                    break
                except asyncio.TimeoutError:
                    continue
            except Exception as e:
                logger.error(f"Unexpected command error: {e}")
                try:
                    await asyncio.wait_for(
                        self.shutdown_manager.wait_for_shutdown(), timeout=1.0
                    )
                    break
                except asyncio.TimeoutError:
                    continue

        await self._cleanup_market_task()

    async def _handle_command(self, cmd: str, bot):
        """Handle individual commands"""
        if cmd == "START":
            if not bot.is_running:
                bot.start_trading()
                logger.info("Bot started")

            if not self._market_data_task or self._market_data_task.done():
                from handlers.market_handler import MarketHandler

                market_handler = MarketHandler(
                    self.shutdown_manager, update_status_callback=self._update_status
                )
                self._market_data_task = asyncio.create_task(
                    market_handler.handle_market_data(bot)
                )
                self.shutdown_manager.register_task(self._market_data_task)

            await self._update_status(bot)

        elif cmd == "STOP":
            logger.info("Bot stopping...")
            bot.stop_trading()
            await self._cleanup_market_task()
            await self._update_status(bot)

    async def _cleanup_market_task(self):
        """Clean up market data task"""
        if self._market_data_task and not self._market_data_task.done():
            logger.info("Cancelling market data handler...")
            self._market_data_task.cancel()
            try:
                await self._market_data_task
            except asyncio.CancelledError:
                pass
            self._market_data_task = None

    async def _update_status(self, bot):
        """Update bot status in Redis"""
        redis_conn = await self.redis_manager.get_connection()
        if not redis_conn:
            return

        try:
            status = bot.get_status()
            await redis_conn.hset("bot_status", mapping=status)
            logger.debug(f"Status updated: {status}")
        except redis.RedisError as e:
            logger.error(f"Failed to update status: {e}")
