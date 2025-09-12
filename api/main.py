import logging
import os

import redis
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Configure logging
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Trading Bot API", version="1.0.0")

# Initialize Redis connection with error handling
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
try:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    r.ping()  # Test connection
    logger.info(f"Connected to Redis at {REDIS_URL}")
except redis.ConnectionError:
    logger.error(f"Failed to connect to Redis at {REDIS_URL}")
    r = None

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


# Serve SPA
@app.get("/")
async def serve_spa():
    return FileResponse("static/index.html")


# API routes
@app.post("/api/bot/start")
async def start_bot():
    if not r:
        raise HTTPException(status_code=500, detail="Redis connection not available")

    try:
        r.lpush("bot_commands", "START")
        logger.info("START command sent to bot")
        return {"status": "command sent"}
    except redis.RedisError as e:
        logger.error(f"Redis error: {e}")
        raise HTTPException(status_code=500, detail="Failed to send command to bot")


@app.post("/api/bot/stop")
async def stop_bot():
    if not r:
        raise HTTPException(status_code=500, detail="Redis connection not available")

    try:
        r.lpush("bot_commands", "STOP")
        logger.info("STOP command sent to bot")
        return {"status": "command sent"}
    except redis.RedisError as e:
        logger.error(f"Redis error: {e}")
        raise HTTPException(status_code=500, detail="Failed to send command to bot")


@app.get("/api/bot/status")
async def get_bot_status():
    if not r:
        raise HTTPException(status_code=500, detail="Redis connection not available")

    try:
        status = r.hgetall("bot_status")
        if not status:
            return {"running": False, "message": "No status available"}
        return status
    except redis.RedisError as e:
        logger.error(f"Redis error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get bot status")


# Health check endpoint
@app.get("/health")
async def health_check():
    redis_status = "connected" if r else "disconnected"
    return {"status": "healthy", "redis": redis_status, "service": "api"}
