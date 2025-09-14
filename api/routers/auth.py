import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from services.auth import (
    GITHUB_CLIENT_ID,
    GITHUB_CLIENT_SECRET,
    OAuthService,
    SessionManager,
    clear_session_cookie,
    create_login_url,
    get_optional_user,
    require_auth,
    set_session_cookie,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.get("/login")
async def login(request: Request):
    """Show login page"""
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured")

    return FileResponse("static/index.html")


@router.get("/github")
async def github_login(request: Request):
    """Redirect to GitHub OAuth login"""
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured")

    login_url = create_login_url(request)
    return RedirectResponse(url=login_url)


@router.get("/callback")
async def auth_callback(request: Request, code: str, state: str):
    """Handle GitHub OAuth callback"""
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured")

    if "oauth_state" not in request.session:
        raise HTTPException(status_code=400, detail="Missing OAuth state")

    session_state = request.session["oauth_state"]

    if request.session.get("oauth_code_used") == code:
        return RedirectResponse(url="/", status_code=302)

    try:
        session_id = OAuthService.process_oauth_callback(code, state, session_state)

        response = RedirectResponse(url="/", status_code=302)
        set_session_cookie(response, session_id)

        request.session.pop("oauth_state", None)
        request.session["oauth_code_used"] = code

        return response

    except HTTPException as e:
        if e.status_code == 403:
            return HTMLResponse(
                content=f"""
                <html>
                <head><title>Access Denied</title></head>
                <body>
                    <h1>Access Denied</h1>
                    <p>{e.detail}</p>
                    <p>Please contact an administrator if you believe
                    this is an error.</p>
                    <a href="/">Return to Home</a>
                </body>
                </html>
                """,
                status_code=403,
            )
        raise

    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        raise HTTPException(
            status_code=400, detail=f"OAuth authentication failed: {str(e)}"
        ) from e


@router.get("/logout")
async def logout(
    request: Request,
    response: Response,
    user: Optional[dict] = Depends(get_optional_user),
):
    """Logout user and destroy session"""
    session_id = request.cookies.get("user_session")
    if session_id:
        SessionManager.delete_session(session_id)

    clear_session_cookie(response)
    response.delete_cookie("session", path="/")

    return RedirectResponse(url="/auth/login", status_code=302)


@router.get("/user")
async def get_user_info(user: dict = Depends(require_auth)):
    """Get current user information"""
    return {
        "username": user.get("username"),
        "name": user.get("name"),
        "avatar_url": user.get("avatar_url"),
        "email": user.get("email"),
    }
