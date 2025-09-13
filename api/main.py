import logging
import os
from typing import Optional

import redis
import requests
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

# Configure logging
from logging_config import setup_logging
from auth import (
    SessionManager,
    create_login_url,
    get_optional_user,
    require_auth,
    is_authorized_user,
    set_session_cookie,
    clear_session_cookie,
    GITHUB_CLIENT_ID,
    GITHUB_CLIENT_SECRET,
    SESSION_SECRET,
)

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Trading Bot API", version="1.0.0")

# Add session middleware
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET or "dev-secret-key")

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


# Serve SPA (redirects to login if not authenticated)
@app.get("/")
async def serve_spa(
    request: Request, user: Optional[dict] = Depends(get_optional_user)
):
    session_cookie = request.cookies.get("session")
    logger.info(
        f"Main route - Session cookie: {session_cookie[:20] if session_cookie else None}..."
    )
    logger.info(f"Main route - User: {user}")
    if not user:
        return RedirectResponse(url="/auth/login", status_code=302)
    return FileResponse("static/index.html")


# Authentication routes
@app.get("/auth/login")
async def login(request: Request):
    """Show login page"""
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured")

    return FileResponse("static/index.html")


@app.get("/auth/github")
async def github_login(request: Request):
    """Redirect to GitHub OAuth login"""
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured")

    login_url = create_login_url(request)
    return RedirectResponse(url=login_url)


@app.get("/auth/callback")
async def auth_callback(request: Request, code: str, state: str):
    """Handle GitHub OAuth callback"""
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured")

    # Verify CSRF state parameter
    if "oauth_state" not in request.session or request.session["oauth_state"] != state:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    # Check if this code has already been processed
    if request.session.get("oauth_code_used") == code:
        return RedirectResponse(url="/", status_code=302)

    # Exchange code for access token
    try:
        token_response = requests.post(
            "https://github.com/login/oauth/access_token",
            {
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )

        logger.info(f"Token response status: {token_response.status_code}")
        logger.info(f"Token response body: {token_response.text}")

        token_data = token_response.json()
        access_token = token_data.get("access_token")

        if "error" in token_data:
            logger.error(f"GitHub OAuth error: {token_data}")
            raise HTTPException(
                status_code=400,
                detail=f"GitHub OAuth error: {token_data.get('error_description', token_data.get('error'))}",
            )

        if not access_token:
            raise HTTPException(status_code=400, detail="Failed to get access token")

        # Get user info from GitHub
        user_response = requests.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_data = user_response.json()

        username = user_data.get("login")
        if not username:
            raise HTTPException(status_code=400, detail="Failed to get GitHub username")

        # Check if user is authorized
        if not is_authorized_user(username):
            return HTMLResponse(
                content=f"""
                <html>
                <head><title>Access Denied</title></head>
                <body>
                    <h1>Access Denied</h1>
                    <p>Sorry, user '{username}' is not authorized to access this application.</p>
                    <p>Please contact an administrator if you believe this is an error.</p>
                    <a href="/">Return to Home</a>
                </body>
                </html>
                """,
                status_code=403,
            )

        # Create session
        session_id = SessionManager.create_session(user_data)

        # Set session cookie and redirect to dashboard
        response = RedirectResponse(url="/", status_code=302)
        set_session_cookie(response, session_id)

        # Clean up OAuth state and mark code as used
        request.session.pop("oauth_state", None)
        request.session["oauth_code_used"] = code

        return response

    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        raise HTTPException(
            status_code=400, detail=f"OAuth authentication failed: {str(e)}"
        )


@app.get("/auth/logout")
async def logout(
    request: Request,
    response: Response,
    user: Optional[dict] = Depends(get_optional_user),
):
    """Logout user and destroy session"""
    session_id = request.cookies.get("user_session")
    if session_id:
        SessionManager.delete_session(session_id)

    # Clear both our session cookie and the SessionMiddleware cookie
    clear_session_cookie(response)
    response.delete_cookie("session", path="/")  # Clear SessionMiddleware cookie

    return RedirectResponse(url="/auth/login", status_code=302)


@app.get("/auth/user")
async def get_user_info(user: dict = Depends(require_auth)):
    """Get current user information"""
    return {
        "username": user.get("username"),
        "name": user.get("name"),
        "avatar_url": user.get("avatar_url"),
        "email": user.get("email"),
    }


# API routes (protected)
@app.post("/api/bot/start")
async def start_bot(user: dict = Depends(require_auth)):
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
async def stop_bot(user: dict = Depends(require_auth)):
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
async def get_bot_status(user: dict = Depends(require_auth)):
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
