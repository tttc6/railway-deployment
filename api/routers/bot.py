from fastapi import APIRouter, Depends
from services.auth import require_auth
from services.bot import bot_service

router = APIRouter(prefix="/api/bot", tags=["bot"])


@router.post("/start")
async def start_bot(user: dict = Depends(require_auth)):
    """Start the trading bot"""
    return bot_service.start_bot()


@router.post("/stop")
async def stop_bot(user: dict = Depends(require_auth)):
    """Stop the trading bot"""
    return bot_service.stop_bot()


@router.get("/status")
async def get_bot_status(user: dict = Depends(require_auth)):
    """Get the current bot status"""
    return bot_service.get_bot_status()
