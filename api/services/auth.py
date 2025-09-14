import json
import logging
import os
import secrets
from typing import Dict, Optional
from urllib.parse import urlencode

import redis
import requests
from fastapi import Cookie, Depends, HTTPException, Request, Response

logger = logging.getLogger(__name__)

# Configuration
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
ALLOWED_GITHUB_USERS = os.getenv("ALLOWED_GITHUB_USERS", "").split(",")
SESSION_SECRET = os.getenv("SESSION_SECRET")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
# Handle Railway's domain format (without protocol) or full URLs
_base_url = os.getenv("BASE_URL", "http://localhost:8000")
if not _base_url.startswith(("http://", "https://")):
    # Assume HTTPS for production domains (Railway, etc.)
    BASE_URL = f"https://{_base_url}"
else:
    BASE_URL = _base_url

# Security configuration - secure by default, opt-out for development
SECURE_COOKIES = os.getenv("SECURE_COOKIES", "true").lower() in ("true", "1", "on")

# OAuth endpoints
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_BASE_URL = "https://api.github.com"

# Initialize Redis connection
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()  # Test connection
    logger.info(f"Auth service connected to Redis at {REDIS_URL}")
except redis.ConnectionError:
    logger.error(f"Auth service failed to connect to Redis at {REDIS_URL}")
    redis_client = None


class SessionManager:
    """Manages user sessions in Redis"""

    SESSION_EXPIRE_TIME = 24 * 60 * 60  # 24 hours in seconds

    @classmethod
    def create_session(cls, user_data: Dict) -> str:
        """Create a new session and return session ID"""
        if not redis_client:
            raise HTTPException(status_code=500, detail="Redis not available")

        session_id = secrets.token_urlsafe(32)
        session_key = f"session:{session_id}"

        session_data = {
            "user_id": user_data.get("id"),
            "username": user_data.get("login"),
            "avatar_url": user_data.get("avatar_url"),
            "name": user_data.get("name"),
            "email": user_data.get("email"),
        }

        redis_client.setex(
            session_key, cls.SESSION_EXPIRE_TIME, json.dumps(session_data)
        )

        logger.info(f"Created session for user: {session_data['username']}")
        return session_id

    @classmethod
    def get_session(cls, session_id: str) -> Optional[Dict]:
        """Get session data by session ID"""
        if not redis_client or not session_id:
            return None

        session_key = f"session:{session_id}"
        try:
            session_data = redis_client.get(session_key)
            if session_data:
                return json.loads(session_data)
        except (redis.RedisError, json.JSONDecodeError) as e:
            logger.error(f"Error getting session {session_id}: {e}")

        return None

    @classmethod
    def delete_session(cls, session_id: str) -> bool:
        """Delete a session"""
        if not redis_client or not session_id:
            return False

        session_key = f"session:{session_id}"
        try:
            result = redis_client.delete(session_key)
            if result:
                logger.info(f"Deleted session: {session_id}")
            return bool(result)
        except redis.RedisError as e:
            logger.error(f"Error deleting session {session_id}: {e}")
            return False

    @classmethod
    def extend_session(cls, session_id: str) -> bool:
        """Extend session expiry time"""
        if not redis_client or not session_id:
            return False

        session_key = f"session:{session_id}"
        try:
            return redis_client.expire(session_key, cls.SESSION_EXPIRE_TIME)
        except redis.RedisError as e:
            logger.error(f"Error extending session {session_id}: {e}")
            return False


class OAuthService:
    """OAuth authentication service"""

    @staticmethod
    def exchange_code_for_token(code: str) -> str:
        """Exchange OAuth code for access token"""
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
                error_desc = token_data.get(
                    "error_description", token_data.get("error")
                )
                raise HTTPException(
                    status_code=400,
                    detail=f"GitHub OAuth error: {error_desc}",
                )

            if not access_token:
                raise HTTPException(
                    status_code=400, detail="Failed to get access token"
                )

            return access_token

        except requests.RequestException as e:
            logger.error(f"Network error during token exchange: {e}")
            raise HTTPException(
                status_code=500, detail="Failed to communicate with GitHub"
            ) from e

    @staticmethod
    def get_user_info(access_token: str) -> Dict:
        """Get user information from GitHub API"""
        try:
            user_response = requests.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            user_response.raise_for_status()
            user_data = user_response.json()

            username = user_data.get("login")
            if not username:
                raise HTTPException(
                    status_code=400, detail="Failed to get GitHub username"
                )

            return user_data

        except requests.RequestException as e:
            logger.error(f"Network error getting user info: {e}")
            raise HTTPException(
                status_code=500, detail="Failed to get user information from GitHub"
            ) from e

    @staticmethod
    def process_oauth_callback(code: str, state: str, session_state: str) -> str:
        """Process OAuth callback and return session ID"""
        if session_state != state:
            raise HTTPException(status_code=400, detail="Invalid state parameter")

        access_token = OAuthService.exchange_code_for_token(code)
        user_data = OAuthService.get_user_info(access_token)

        username = user_data.get("login")
        if not is_authorized_user(username):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"User '{username}' is not authorized to access this application"
                ),
            )

        session_id = SessionManager.create_session(user_data)
        return session_id


# FastAPI Dependencies
def get_current_user(session_id: str = Cookie(None, alias="user_session")) -> Dict:
    """FastAPI dependency to get current authenticated user"""
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_data = SessionManager.get_session(session_id)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    # Extend session on each use
    SessionManager.extend_session(session_id)

    return user_data


def get_optional_user(
    session_id: str = Cookie(None, alias="user_session"),
) -> Optional[Dict]:
    """FastAPI dependency to optionally get current authenticated user"""
    if not session_id:
        return None

    user_data = SessionManager.get_session(session_id)
    if user_data:
        # Extend session on each use
        SessionManager.extend_session(session_id)

    return user_data


def require_auth(request: Request, user: Dict = Depends(get_current_user)) -> Dict:
    """FastAPI dependency that ensures user is authenticated"""
    # This dependency will automatically raise 401 if get_current_user fails
    return user


# Utility Functions
def create_login_url(request: Request) -> str:
    """Create GitHub OAuth login URL with state parameter for CSRF protection"""
    state = secrets.token_urlsafe(32)

    # Store state in session temporarily (we'll use a simple in-memory cache for this)
    # In production, you might want to store this in Redis with a short TTL
    request.session["oauth_state"] = state

    # Use explicit BASE_URL instead of request-based URL construction
    # This ensures consistent redirect URIs regardless of proxy headers
    redirect_uri = f"{BASE_URL.rstrip('/')}/auth/callback"

    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": "user:email",
        "state": state,
    }

    return f"https://github.com/login/oauth/authorize?{urlencode(params)}"


def is_authorized_user(username: str) -> bool:
    """Check if GitHub username is in allowed users list"""
    return username in ALLOWED_GITHUB_USERS


def set_session_cookie(response: Response, session_id: str) -> None:
    """Set secure session cookie"""
    response.set_cookie(
        key="user_session",
        value=session_id,
        max_age=SessionManager.SESSION_EXPIRE_TIME,
        httponly=True,
        secure=SECURE_COOKIES,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Clear session cookie"""
    response.delete_cookie(
        key="user_session",
        path="/",
        httponly=True,
        secure=SECURE_COOKIES,
        samesite="lax",
    )
