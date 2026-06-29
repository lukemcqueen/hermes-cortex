---
title: JWT Auth System
description: Complete JWT authentication system with access + refresh tokens. FastAPI login/signup/refresh/logout endpoints, bcrypt password hashing, middleware-protected routes, React login form with token storage and auto-refresh.
language: python
tags: [auth, jwt, fullstack, login, security]
---

# JWT Auth System

A production-grade authentication system with JWT access and refresh tokens. Features FastAPI endpoints for signup, login, token refresh, and logout, with bcrypt password hashing and a React frontend that auto-refreshs tokens.

## Architecture

```
┌─────────────┐      Access Token (15 min)      ┌──────────────┐
│  React App  │ ──────────────────────────────▶  │  FastAPI     │
│  (Frontend) │ ◀──────────────────────────────  │  Backend     │
│             │      Refresh Token (7 days)      │              │
│  localStorage│                                 │  bcrypt pw   │
│  auto-refresh│                                 │  JWT verify  │
└─────────────┘                                  └──────┬───────┘
                                                        │
                                                ┌───────┴───────┐
                                                │  PostgreSQL   │
                                                │  (users table)│
                                                └───────────────┘
```

## Backend

### `backend/app/auth/__init__.py`

```python
from app.auth.config import (
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
from app.auth.dependencies import get_current_user, require_auth
from app.auth.handlers import (
    create_access_token,
    create_refresh_token,
    verify_token,
    hash_password,
    verify_password,
)
from app.auth.schemas import (
    UserCreate,
    UserLogin,
    UserResponse,
    TokenResponse,
    TokenRefresh,
)
```

### `backend/app/auth/config.py`

```python
import os
from datetime import timedelta

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-production-use-a-real-secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_EXPIRE_DAYS", "7"))

ACCESS_TOKEN_EXPIRE_DELTA = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
REFRESH_TOKEN_EXPIRE_DELTA = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
```

### `backend/app/auth/models.py`

```python
from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

### `backend/app/auth/schemas.py`

```python
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional


class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=8, max_length=128)


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class TokenRefresh(BaseModel):
    refresh_token: str
```

### `backend/app/auth/handlers.py`

```python
from datetime import datetime, timezone
from jose import jwt, JWTError
from passlib.context import CryptContext
from app.auth.config import (
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_DELTA,
    REFRESH_TOKEN_EXPIRE_DELTA,
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + ACCESS_TOKEN_EXPIRE_DELTA
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + REFRESH_TOKEN_EXPIRE_DELTA
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str, expected_type: str = "access") -> dict | None:
    """Verify a JWT token. Returns payload dict on success, None on failure."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != expected_type:
            return None
        return payload
    except JWTError:
        return None


def get_token_expiry(token: str) -> datetime | None:
    """Extract expiry from a token without verifying signature."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
        exp = payload.get("exp")
        return datetime.fromtimestamp(exp, tz=timezone.utc) if exp else None
    except JWTError:
        return None
```

### `backend/app/auth/dependencies.py`

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.handlers import verify_token
from app.auth.models import User

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Extract and validate the current user from the access token."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_token(credentials.credentials, expected_type="access")
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or deactivated")

    return user


def require_auth(user: User = Depends(get_current_user)) -> User:
    """Stricter dependency — ensures a valid authenticated user."""
    return user
```

### `backend/app/auth/routes.py`

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database import get_db
from app.auth.models import User, RefreshToken
from app.auth.schemas import UserCreate, UserLogin, UserResponse, TokenResponse, TokenRefresh
from app.auth.handlers import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token,
    get_token_expiry,
)
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user."""
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=409, detail="Username already taken")

    user = User(
        email=data.email,
        username=data.username,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(data: UserLogin, db: Session = Depends(get_db)):
    """Authenticate and return JWT tokens."""
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account deactivated")

    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    # Store refresh token in DB for revocation
    expires_at = get_token_expiry(refresh_token)
    db_refresh = RefreshToken(
        token=refresh_token,
        user_id=user.id,
        expires_at=expires_at,
    )
    db.add(db_refresh)
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=900,  # 15 minutes in seconds
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(data: TokenRefresh, db: Session = Depends(get_db)):
    """Refresh an access token using a valid refresh token."""
    payload = verify_token(data.refresh_token, expected_type="refresh")
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user_id = payload.get("sub")
    stored = db.query(RefreshToken).filter(
        RefreshToken.token == data.refresh_token,
        RefreshToken.revoked == False,
    ).first()
    if not stored:
        raise HTTPException(status_code=401, detail="Refresh token revoked or not found")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or deactivated")

    # Revoke old refresh token (rotation)
    stored.revoked = True
    db.flush()

    # Issue new tokens
    new_access = create_access_token({"sub": str(user.id)})
    new_refresh = create_refresh_token({"sub": str(user.id)})
    expires_at = get_token_expiry(new_refresh)
    db_refresh = RefreshToken(token=new_refresh, user_id=user.id, expires_at=expires_at)
    db.add(db_refresh)
    db.commit()

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        expires_in=900,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    data: TokenRefresh,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke a refresh token (logout)."""
    stored = db.query(RefreshToken).filter(
        RefreshToken.token == data.refresh_token,
        RefreshToken.user_id == user.id,
        RefreshToken.revoked == False,
    ).first()
    if stored:
        stored.revoked = True
        db.commit()
    return None


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    """Get current authenticated user profile."""
    return user
```

### `backend/app/main.py`

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.auth.routes import router as auth_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Auth API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
```

## React Frontend

### `frontend/src/auth/AuthContext.tsx`

```typescript
import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";

interface User {
  id: number;
  email: string;
  username: string;
}

interface Tokens {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
}

interface AuthContextType {
  user: User | null;
  tokens: Tokens | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  signup: (email: string, username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const STORAGE_KEY = "auth_tokens";

function storeTokens(tokens: Tokens) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens));
}

function loadTokens(): Tokens | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function clearTokens() {
  localStorage.removeItem(STORAGE_KEY);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [tokens, setTokens] = useState<Tokens | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchUser = useCallback(async (accessToken: string): Promise<User> => {
    const res = await fetch(`${API_BASE}/api/auth/me`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!res.ok) throw new Error("Failed to fetch user");
    return res.json();
  }, []);

  const refreshTokens = useCallback(async (refreshToken: string): Promise<Tokens> => {
    const res = await fetch(`${API_BASE}/api/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) throw new Error("Token refresh failed");
    const data = await res.json();
    return {
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      expiresIn: data.expires_in,
    };
  }, []);

  // Restore session on mount
  useEffect(() => {
    (async () => {
      const stored = loadTokens();
      if (!stored) {
        setLoading(false);
        return;
      }

      try {
        const user = await fetchUser(stored.accessToken);
        setUser(user);
        setTokens(stored);
      } catch {
        // Access token expired — try refresh
        try {
          const newTokens = await refreshTokens(stored.refreshToken);
          storeTokens(newTokens);
          setTokens(newTokens);
          const user = await fetchUser(newTokens.accessToken);
          setUser(user);
        } catch {
          clearTokens();
          setTokens(null);
          setUser(null);
        }
      }
      setLoading(false);
    })();
  }, [fetchUser, refreshTokens]);

  // Auto-refresh before token expires
  useEffect(() => {
    if (!tokens) return;

    // Refresh 1 minute before expiry (expiresIn is seconds)
    const refreshMs = Math.max((tokens.expiresIn - 60) * 1000, 30000);
    const interval = setInterval(async () => {
      try {
        const newTokens = await refreshTokens(tokens.refreshToken);
        storeTokens(newTokens);
        setTokens(newTokens);
      } catch {
        // Refresh failed — logout
        clearTokens();
        setTokens(null);
        setUser(null);
      }
    }, refreshMs);

    return () => clearInterval(interval);
  }, [tokens, refreshTokens]);

  const login = async (username: string, password: string) => {
    const res = await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const err = await res.text();
      throw new Error(err || "Login failed");
    }
    const data = await res.json();
    const newTokens: Tokens = {
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      expiresIn: data.expires_in,
    };
    storeTokens(newTokens);
    setTokens(newTokens);
    const user = await fetchUser(newTokens.accessToken);
    setUser(user);
  };

  const signup = async (email: string, username: string, password: string) => {
    const res = await fetch(`${API_BASE}/api/auth/signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, username, password }),
    });
    if (!res.ok) {
      const err = await res.text();
      throw new Error(err || "Signup failed");
    }
  };

  const logout = async () => {
    if (tokens) {
      try {
        await fetch(`${API_BASE}/api/auth/logout`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${tokens.accessToken}`,
          },
          body: JSON.stringify({ refresh_token: tokens.refreshToken }),
        });
      } catch {
        // Best-effort
      }
    }
    clearTokens();
    setTokens(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, tokens, loading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
```

### `frontend/src/auth/LoginForm.tsx`

```typescript
import React, { useState } from "react";
import { useAuth } from "./AuthContext";

interface Props {
  onSuccess?: () => void;
  onSwitchToSignup?: () => void;
}

export function LoginForm({ onSuccess, onSwitchToSignup }: Props) {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(username, password);
      onSuccess?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <h2>Login</h2>
      {error && <div style={{ color: "red" }}>{error}</div>}
      <div>
        <label>Username</label>
        <input
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
          autoFocus
        />
      </div>
      <div>
        <label>Password</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </div>
      <button type="submit" disabled={loading}>
        {loading ? "Logging in..." : "Login"}
      </button>
      {onSwitchToSignup && (
        <p>
          Don't have an account?{" "}
          <button type="button" onClick={onSwitchToSignup}>
            Sign up
          </button>
        </p>
      )}
    </form>
  );
}
```

### `frontend/src/auth/SignupForm.tsx`

```typescript
import React, { useState } from "react";
import { useAuth } from "./AuthContext";

interface Props {
  onSuccess?: () => void;
  onSwitchToLogin?: () => void;
}

export function SignupForm({ onSuccess, onSwitchToLogin }: Props) {
  const { signup } = useAuth();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await signup(email, username, password);
      onSuccess?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <h2>Sign Up</h2>
      {error && <div style={{ color: "red" }}>{error}</div>}
      <div>
        <label>Email</label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
      </div>
      <div>
        <label>Username</label>
        <input
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
          minLength={3}
        />
      </div>
      <div>
        <label>Password</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={8}
        />
      </div>
      <button type="submit" disabled={loading}>
        {loading ? "Creating account..." : "Sign Up"}
      </button>
      {onSwitchToLogin && (
        <p>
          Already have an account?{" "}
          <button type="button" onClick={onSwitchToLogin}>
            Log in
          </button>
        </p>
      )}
    </form>
  );
}
```

### `frontend/src/auth/ProtectedRoute.tsx`

```typescript
import React, { ReactNode } from "react";
import { useAuth } from "./AuthContext";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

export function ProtectedRoute({ children, fallback }: Props) {
  const { user, loading } = useAuth();

  if (loading) return <div>Loading...</div>;
  if (!user) return <>{fallback || <div>Please log in to access this page.</div>}</>;
  return <>{children}</>;
}
```

### `frontend/src/App.tsx`

```typescript
import React, { useState } from "react";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { LoginForm } from "./auth/LoginForm";
import { SignupForm } from "./auth/SignupForm";
import { ProtectedRoute } from "./auth/ProtectedRoute";

function AuthGate() {
  const { user, logout } = useAuth();
  const [mode, setMode] = useState<"login" | "signup">("login");

  if (user) {
    return (
      <div>
        <h1>Welcome, {user.username}!</h1>
        <p>Email: {user.email}</p>
        <button onClick={logout}>Logout</button>
      </div>
    );
  }

  return mode === "login" ? (
    <LoginForm
      onSwitchToSignup={() => setMode("signup")}
    />
  ) : (
    <SignupForm
      onSwitchToLogin={() => setMode("login")}
      onSuccess={() => setMode("login")}
    />
  );
}

function App() {
  return (
    <AuthProvider>
      <div style={{ maxWidth: "400px", margin: "2rem auto" }}>
        <AuthGate />
        <hr />
        <ProtectedRoute fallback={<p>🔒 Protected content — login to see</p>}>
          <div style={{ border: "1px solid green", padding: "1rem" }}>
            🛡️ This is protected content visible only to authenticated users.
          </div>
        </ProtectedRoute>
      </div>
    </AuthProvider>
  );
}

export default App;
```

## Key Security Patterns

| Pattern | Implementation |
|---------|---------------|
| **Password hashing** | bcrypt via `passlib` |
| **Access token** | Short-lived (15 min), signed with HS256 |
| **Refresh token** | Long-lived (7 days), stored in DB, revocable |
| **Token rotation** | Each refresh revokes the old refresh token |
| **Auto-refresh** | React context refreshes 1 min before expiry |
| **Secure storage** | `localStorage` (consider httpOnly cookies in production) |
| **Route protection** | FastAPI `Depends(get_current_user)` middleware |

## Running

```bash
# Backend
pip install fastapi uvicorn[standard] sqlalchemy python-jose[cryptography] passlib[bcrypt] pydantic[email]
uvicorn app.main:app --reload

# Frontend
npm install
npm run dev
```