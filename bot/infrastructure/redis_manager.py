import asyncio
import logging
import os
from typing import Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class RedisManager:
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis: Optional[redis.Redis] = None
        self._connection_lock = asyncio.Lock()

    async def connect(
        self, max_retries: int = 5, shutdown_event: Optional[asyncio.Event] = None
    ):
        """Initialize async Redis connection with retry logic"""
        async with self._connection_lock:
            if self.redis:
                return

            retry_delay = 1
            for attempt in range(max_retries):
                if shutdown_event and shutdown_event.is_set():
                    logger.info(
                        "Shutdown requested, stopping Redis connection attempts"
                    )
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
                            if shutdown_event:
                                await asyncio.wait_for(
                                    shutdown_event.wait(), timeout=retry_delay
                                )
                                return
                            else:
                                await asyncio.sleep(retry_delay)
                        except asyncio.TimeoutError:
                            pass
                        retry_delay = min(retry_delay * 2, 30)
                        continue
                    else:
                        logger.error(
                            f"Failed to connect to Redis after {max_retries} "
                            f"attempts: {e}"
                        )

    async def ensure_connection(self, shutdown_event: Optional[asyncio.Event] = None):
        """Ensure Redis connection is available, reconnect if needed"""
        if not self.redis:
            await self.connect(shutdown_event=shutdown_event)

        if self.redis:
            try:
                await self.redis.ping()
            except redis.ConnectionError:
                logger.warning("Redis connection lost, attempting to reconnect...")
                self.redis = None
                await self.connect(shutdown_event=shutdown_event)

    async def get_connection(self) -> Optional[redis.Redis]:
        """Get the Redis connection, ensuring it's healthy"""
        await self.ensure_connection()
        return self.redis

    async def close(self):
        """Close the Redis connection"""
        if self.redis:
            await self.redis.aclose()
            self.redis = None
            logger.info("Redis connection closed")

    @property
    def is_connected(self) -> bool:
        """Check if Redis is connected"""
        return self.redis is not None
