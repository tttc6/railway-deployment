import logging
from typing import Optional

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from logging_config import setup_logging
from routers import auth, bot
from services.auth import SESSION_SECRET, get_optional_user
from services.bot import bot_service
from starlette.middleware.sessions import SessionMiddleware

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Trading Bot API", version="1.0.0")

# Add session middleware
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

# Include routers
app.include_router(auth.router)
app.include_router(bot.router)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


# Serve SPA (redirects to login if not authenticated)
@app.get("/")
async def serve_spa(
    request: Request, user: Optional[dict] = Depends(get_optional_user)
):
    session_cookie = request.cookies.get("session")
    cookie_display = session_cookie[:20] if session_cookie else None
    logger.info(f"Main route - Session cookie: {cookie_display}...")
    logger.info(f"Main route - User: {user}")
    if not user:
        return RedirectResponse(url="/auth/login", status_code=302)
    return FileResponse("static/index.html")


# Health check endpoint
@app.get("/health")
async def health_check():
    redis_status = bot_service.get_health_status()
    return {"status": "healthy", "redis": redis_status, "service": "api"}
