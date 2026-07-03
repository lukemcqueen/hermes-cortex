---
language: python
tags: [oauth2, google, social-login, authentication]
title: OAuth2 Google Login
description: Redirect to Google consent, callback handler, state param for CSRF, user info endpoint, session creation
source: pattern
---

# OAuth2 Google Login

## Dependencies

```python
# pip install httpx authlib fastapi[standard]
```

## Configuration & Constants

```python
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

app = FastAPI()

# Google OAuth2 configuration
GOOGLE_CLIENT_ID = "your-google-client-id"
GOOGLE_CLIENT_SECRET = "your-google-client-secret"
GOOGLE_REDIRECT_URI = "http://localhost:8000/auth/google/callback"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

SCOPES = [
    "openid",
    "email",
    "profile",
]

SESSION_SECRET = "your-session-secret-change-in-production"
```

## Redirect to Google Consent

```python
from fastapi.responses import RedirectResponse


@app.get("/auth/google/login")
async def google_login(request: Request):
    """
    Redirect the user to Google's OAuth2 consent page.
    Includes a state parameter for CSRF protection.
    """
    # Generate a random state value for CSRF protection
    state = secrets.token_urlsafe(32)

    # Store state in a short-lived cookie or session for verification later
    # In production, store this in a signed cookie or Redis with TTL
    response = RedirectResponse(url=None, status_code=302)
    response.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        secure=True,  # Set to False for localhost HTTP
        samesite="lax",
        max_age=600,  # 10 minutes
        path="/",
    )

    # Build Google OAuth2 URL
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
        "access_type": "offline",  # Get refresh token
        "prompt": "consent",       # Force consent screen every time
    }
    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    auth_url = f"{GOOGLE_AUTH_URL}?{query_string}"

    response.headers["Location"] = auth_url
    return response
```

## Callback Handler

```python
@app.get("/auth/google/callback")
async def google_callback(request: Request, code: str, state: str):
    """
    Handle the OAuth2 callback from Google.
    1. Verify state parameter matches (CSRF protection)
    2. Exchange authorization code for tokens
    3. Fetch user info from Google
    4. Create or look up user in database
    5. Return session tokens
    """
    # --- Step 1: Verify state (CSRF protection) ---
    stored_state = request.cookies.get("oauth_state")
    if not stored_state or stored_state != state:
        raise HTTPException(status_code=400, detail="Invalid state parameter — possible CSRF attack")

    # --- Step 2: Exchange authorization code for tokens ---
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
        )

    if token_response.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to exchange authorization code")

    token_data = token_response.json()
    access_token = token_data.get("access_token")
    id_token = token_data.get("id_token")
    refresh_token = token_data.get("refresh_token")  # May not always be returned

    # --- Step 3: Fetch user info from Google ---
    async with httpx.AsyncClient() as client:
        userinfo_response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if userinfo_response.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to fetch user info")

    user_info = userinfo_response.json()
    # user_info contains: id, email, verified_email, name, given_name, family_name, picture, locale

    # --- Step 4: Create or look up user in database ---
    # In production, check if user exists by google_id or email
    # user = await db.get_user_by_google_id(user_info["id"])
    # if not user:
    #     user = await db.create_user(
    #         google_id=user_info["id"],
    #         email=user_info["email"],
    #         name=user_info["name"],
    #         avatar_url=user_info.get("picture"),
    #     )

    # --- Step 5: Create session ---
    # For simplicity, we create a session token
    session_token = secrets.token_urlsafe(48)
    # Store session in Redis or database:
    # await redis.setex(
    #     f"session:{session_token}",
    #     timedelta(days=7),
    #     json.dumps({"user_id": user.id, "google_id": user_info["id"], "email": user_info["email"]})
    # )

    # Clear the oauth_state cookie and set session cookie
    response = RedirectResponse(url="/auth/me", status_code=302)
    response.delete_cookie("oauth_state", path="/")
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=7 * 86400,  # 7 days
        path="/",
    )

    return response
```

## User Info Endpoint

```python
from fastapi import Depends, HTTPException, Request, status
from typing import Optional


async def get_current_user(request: Request) -> dict:
    """Extract the current user from the session cookie."""
    session_token = request.cookies.get("session_token")
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    # In production, look up session in Redis/database
    # session_data = await redis.get(f"session:{session_token}")
    # if not session_data:
    #     raise HTTPException(status_code=401, detail="Session expired")
    # return json.loads(session_data)

    # Example return for demo purposes
    return {"user_id": 1, "email": "user@example.com", "name": "Demo User"}


@app.get("/auth/me")
async def get_user_info(current_user: dict = Depends(get_current_user)):
    """Return the authenticated user's profile info."""
    return {
        "user": current_user,
        "provider": "google",
        "authenticated": True,
    }


@app.post("/auth/logout")
async def logout(response: Response):
    """Clear the session cookie to logout."""
    response.delete_cookie("session_token", path="/")
    return {"message": "Successfully logged out"}
```

## Full OAuth2 Flow with Authlib (Simplified)

```python
# Alternative: using the authlib library for a more streamlined flow
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config

config = Config(environ={"GOOGLE_CLIENT_ID": GOOGLE_CLIENT_ID, "GOOGLE_CLIENT_SECRET": GOOGLE_CLIENT_SECRET})
oauth = OAuth(config)

oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


@app.get("/auth/google/login-v2")
async def google_login_v2(request: Request):
    """Simplified redirect using Authlib."""
    redirect_uri = request.url_for("google_callback_v2")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/google/callback-v2")
async def google_callback_v2(request: Request):
    """Simplified callback using Authlib."""
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo")
    if not user_info:
        user_info = await oauth.google.parse_id_token(request, token)

    # user_info contains all the Google profile data
    return {"user": user_info, "token": token}
```