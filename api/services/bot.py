import logging
import os
from typing import Dict

import redis
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class BotService:
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis_client = self._init_redis_connection()

    def _init_redis_connection(self) -> redis.Redis:
        """Initialize Redis connection with error handling"""
        try:
            client = redis.from_url(self.redis_url, decode_responses=True)
            client.ping()
            logger.info(f"Bot service connected to Redis at {self.redis_url}")
            return client
        except redis.ConnectionError:
            logger.error(f"Bot service failed to connect to Redis at {self.redis_url}")
            return None

    def _ensure_redis_connection(self):
        """Ensure Redis connection is available"""
        if not self.redis_client:
            raise HTTPException(
                status_code=500, detail="Redis connection not available"
            )

    def send_command(self, command: str) -> Dict[str, str]:
        """Send a command to the bot via Redis"""
        self._ensure_redis_connection()

        try:
            self.redis_client.lpush("bot_commands", command)
            logger.info(f"{command} command sent to bot")
            return {"status": "command sent"}
        except redis.RedisError as e:
            logger.error(f"Redis error sending command {command}: {e}")
            raise HTTPException(
                status_code=500, detail="Failed to send command to bot"
            ) from e

    def start_bot(self) -> Dict[str, str]:
        """Start the bot"""
        return self.send_command("START")

    def stop_bot(self) -> Dict[str, str]:
        """Stop the bot"""
        return self.send_command("STOP")

    def get_bot_status(self) -> Dict:
        """Get the current bot status"""
        self._ensure_redis_connection()

        try:
            status = self.redis_client.hgetall("bot_status")
            if not status:
                return {"running": False, "message": "No status available"}
            return status
        except redis.RedisError as e:
            logger.error(f"Redis error getting bot status: {e}")
            raise HTTPException(
                status_code=500, detail="Failed to get bot status"
            ) from e

    def get_health_status(self) -> str:
        """Get Redis connection health status"""
        return "connected" if self.redis_client else "disconnected"


bot_service = BotService()
