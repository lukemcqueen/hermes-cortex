---
language: python
tags: [auth, jwt, authentication, security, api]
title: JWT Authentication
description: Login endpoint, access + refresh tokens, verify middleware (FastAPI + Express examples), token blacklist, secure cookies
source: pattern
---

# JWT Authentication

## FastAPI Login Endpoint with Access & Refresh Tokens

```python
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

app = FastAPI()
security = HTTPBearer()

# Configuration
SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str
    exp: datetime
    type: str = "access"


class UserLogin(BaseModel):
    username: str
    password: str


def create_access_token(subject: str) -> str:
    """Create a short-lived access token."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": subject, "exp": expire, "type": "access"}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(subject: str) -> str:
    """Create a long-lived refresh token."""
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {"sub": subject, "exp": expire, "type": "refresh"}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


@app.post("/auth/login", response_model=Token)
async def login(credentials: UserLogin):
    """Authenticate user and return access + refresh tokens."""
    # In production, verify against database with hashed passwords
    if credentials.username != "admin" or credentials.password != "secret":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    return Token(
        access_token=create_access_token(credentials.username),
        refresh_token=create_refresh_token(credentials.username),
    )


@app.post("/auth/refresh", response_model=Token)
async def refresh_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Exchange a valid refresh token for a new access + refresh token pair."""
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type; refresh token required",
        )

    subject = payload["sub"]
    return Token(
        access_token=create_access_token(subject),
        refresh_token=create_refresh_token(subject),
    )
```

## Verify Middleware (FastAPI)

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Dependency that extracts and validates the current user from JWT."""
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token required",
        )
    return {"username": payload["sub"], "token_type": payload["type"]}


@app.get("/protected")
async def protected_endpoint(current_user: dict = Depends(get_current_user)):
    """Only accessible with a valid access token."""
    return {"message": f"Hello, {current_user['username']}!", "user": current_user}
```

## Verify Middleware (Express.js)

```typescript
import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';

const SECRET_KEY = process.env.JWT_SECRET || 'your-secret-key';

interface AuthRequest extends Request {
  user?: { userId: string; role?: string };
}

function authenticateToken(req: AuthRequest, res: Response, next: NextFunction) {
  const authHeader = req.headers['authorization'];
  const token = authHeader && authHeader.split(' ')[1]; // Bearer TOKEN

  if (!token) {
    return res.status(401).json({ error: 'Access token required' });
  }

  try {
    const decoded = jwt.verify(token, SECRET_KEY) as { userId: string; role?: string };
    req.user = decoded;
    next();
  } catch (err) {
    if (err instanceof jwt.TokenExpiredError) {
      return res.status(401).json({ error: 'Token has expired' });
    }
    return res.status(403).json({ error: 'Invalid token' });
  }
}

// Usage
app.get('/api/protected', authenticateToken, (req: AuthRequest, res: Response) => {
  res.json({ message: `Hello, user ${req.user!.userId}` });
});

// Login endpoint
app.post('/api/login', (req: Request, res: Response) => {
  const { username, password } = req.body;
  // Verify credentials against database...

  const accessToken = jwt.sign(
    { userId: '123', role: 'user' },
    SECRET_KEY,
    { expiresIn: '30m' }
  );
  const refreshToken = jwt.sign(
    { userId: '123' },
    SECRET_KEY,
    { expiresIn: '7d' }
  );

  res.json({ access_token: accessToken, refresh_token: refreshToken });
});
```

## Token Blacklist

```python
import redis.asyncio as aioredis
from datetime import timedelta

# Token blacklist using Redis (invalidate tokens before expiry)
redis_client = aioredis.from_url("redis://localhost:6379", decode_responses=True)


async def blacklist_token(jti: str, expires_in: int):
    """Add a token's JTI to the blacklist for its remaining lifetime."""
    await redis_client.setex(f"blacklist:{jti}", timedelta(seconds=expires_in), "true")


async def is_token_blacklisted(jti: str) -> bool:
    """Check if a token has been revoked."""
    return await redis_client.exists(f"blacklist:{jti}") > 0


async def get_current_user_with_blacklist(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Verify JWT and check blacklist."""
    payload = decode_token(credentials.credentials)
    jti = payload.get("jti", "")
    if await is_token_blacklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )
    return {"username": payload["sub"]}


@app.post("/auth/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Logout by blacklisting the current access token."""
    payload = decode_token(credentials.credentials)
    jti = payload.get("jti")
    exp = payload.get("exp")
    if jti and exp:
        remaining = exp - int(datetime.now(timezone.utc).timestamp())
        await blacklist_token(jti, max(remaining, 0))
    return {"message": "Successfully logged out"}
```

## Secure Cookies

```python
from fastapi.responses import JSONResponse


@app.post("/auth/login-cookie")
async def login_with_cookies(credentials: UserLogin):
    """Set tokens as HTTP-only secure cookies instead of returning in body."""
    if credentials.username != "admin" or credentials.password != "secret":
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(credentials.username)
    refresh_token = create_refresh_token(credentials.username)

    response = JSONResponse(content={"message": "Login successful"})
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,      # Not accessible via JavaScript
        secure=True,        # HTTPS only
        samesite="lax",     # CSRF protection
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/auth/refresh",
    )
    return response


@app.post("/auth/logout-cookie")
async def logout_with_cookies():
    """Clear auth cookies to logout."""
    response = JSONResponse(content={"message": "Logged out"})
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/auth/refresh")
    return response
```