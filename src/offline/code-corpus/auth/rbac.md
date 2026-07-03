---
language: python
tags: [rbac, authorization, roles, permissions, security]
title: Role-Based Access Control (RBAC)
description: Role/permission models, middleware checking roles, FastAPI dependency for RBAC, Express middleware, permission inheritance
source: pattern
---

# Role-Based Access Control (RBAC)

## Role / Permission Models

```python
from enum import Enum
from typing import Dict, List, Set
from pydantic import BaseModel


class Role(str, Enum):
    ADMIN = "admin"
    MODERATOR = "moderator"
    USER = "user"
    GUEST = "guest"


class Permission(str, Enum):
    # User permissions
    READ_PROFILE = "read:profile"
    UPDATE_PROFILE = "update:profile"
    DELETE_PROFILE = "delete:profile"

    # Content permissions
    CREATE_POST = "create:post"
    READ_POST = "read:post"
    UPDATE_POST = "update:post"
    DELETE_POST = "delete:post"

    # Moderation permissions
    MODERATE_CONTENT = "moderate:content"
    BAN_USER = "ban:user"

    # Admin permissions
    MANAGE_USERS = "manage:users"
    MANAGE_ROLES = "manage:roles"
    VIEW_ANALYTICS = "view:analytics"
    SYSTEM_CONFIG = "system:config"


# Permission inheritance / hierarchy
# Each role inherits permissions from its parent (if any)
ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
    Role.ADMIN: {
        Permission.READ_PROFILE,
        Permission.UPDATE_PROFILE,
        Permission.DELETE_PROFILE,
        Permission.CREATE_POST,
        Permission.READ_POST,
        Permission.UPDATE_POST,
        Permission.DELETE_POST,
        Permission.MODERATE_CONTENT,
        Permission.BAN_USER,
        Permission.MANAGE_USERS,
        Permission.MANAGE_ROLES,
        Permission.VIEW_ANALYTICS,
        Permission.SYSTEM_CONFIG,
    },
    Role.MODERATOR: {
        Permission.READ_PROFILE,
        Permission.UPDATE_PROFILE,
        Permission.CREATE_POST,
        Permission.READ_POST,
        Permission.UPDATE_POST,
        Permission.DELETE_POST,
        Permission.MODERATE_CONTENT,
        Permission.BAN_USER,
        Permission.VIEW_ANALYTICS,
    },
    Role.USER: {
        Permission.READ_PROFILE,
        Permission.UPDATE_PROFILE,
        Permission.CREATE_POST,
        Permission.READ_POST,
        Permission.UPDATE_POST,
        Permission.DELETE_POST,
    },
    Role.GUEST: {
        Permission.READ_PROFILE,
        Permission.READ_POST,
    },
}


def get_role_hierarchy(role: Role) -> List[Role]:
    """Return the role and all roles it inherits from (admin > mod > user > guest)."""
    hierarchy = {
        Role.ADMIN: [Role.ADMIN, Role.MODERATOR, Role.USER, Role.GUEST],
        Role.MODERATOR: [Role.MODERATOR, Role.USER, Role.GUEST],
        Role.USER: [Role.USER, Role.GUEST],
        Role.GUEST: [Role.GUEST],
    }
    return hierarchy.get(role, [role])


def get_effective_permissions(role: Role) -> Set[Permission]:
    """Get all permissions for a role, including inherited ones."""
    permissions: Set[Permission] = set()
    for r in get_role_hierarchy(role):
        permissions.update(ROLE_PERMISSIONS.get(r, set()))
    return permissions


class User(BaseModel):
    id: str
    username: str
    role: Role
    custom_permissions: Set[Permission] = set()

    def has_permission(self, permission: Permission) -> bool:
        """Check if user has a specific permission (role-based + custom)."""
        return permission in get_effective_permissions(self.role) or permission in self.custom_permissions
```

## FastAPI RBAC Middleware & Dependencies

```python
from functools import wraps
from typing import List, Optional, Set

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

app = FastAPI()
security = HTTPBearer()


# --- Mock database ---
async def get_user_from_token(token: str) -> Optional[User]:
    """Look up user from auth token. Replace with real DB query."""
    # In production: decode JWT, query database
    if token == "admin-token":
        return User(id="1", username="admin", role=Role.ADMIN)
    elif token == "mod-token":
        return User(id="2", username="moderator", role=Role.MODERATOR)
    elif token == "user-token":
        return User(id="3", username="user", role=Role.USER)
    return None


# --- Auth dependency ---
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """Dependency that extracts the current authenticated user."""
    user = await get_user_from_token(credentials.credentials)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    return user


# --- RBAC dependency factory ---
class RBAC:
    """
    FastAPI dependency for role-based access control.

    Usage:
        @app.get("/admin-only")
        async def admin_endpoint(user: User = Depends(RBAC(Role.ADMIN))):
            ...

        @app.get("/moderate")
        async def moderate_endpoint(user: User = Depends(RBAC(Role.MODERATOR))):
            ...
    """

    def __init__(
        self,
        required_role: Optional[Role] = None,
        required_permissions: Optional[List[Permission]] = None,
    ):
        self.required_role = required_role
        self.required_permissions = required_permissions or []

    async def __call__(self, user: User = Depends(get_current_user)) -> User:
        # Check role requirement
        if self.required_role:
            allowed_roles = get_role_hierarchy(self.required_role)
            if user.role not in allowed_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Role '{user.role.value}' is not authorized. Required: '{self.required_role.value}' or higher",
                )

        # Check permission requirements
        for perm in self.required_permissions:
            if not user.has_permission(perm):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions. Missing: '{perm.value}'",
                )

        return user


# Alternative: Permission-based dependency
def require_permissions(*permissions: Permission):
    """Decorator-style dependency factory for requiring specific permissions."""

    class PermissionChecker:
        def __init__(self):
            self.required = set(permissions)

        async def __call__(self, user: User = Depends(get_current_user)) -> User:
            effective = get_effective_permissions(user.role).union(user.custom_permissions)
            missing = self.required - effective
            if missing:
                names = ", ".join(p.value for p in missing)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing permissions: {names}",
                )
            return user

    return PermissionChecker()


# --- Example endpoints with RBAC ---
@app.get("/api/users/me")
async def get_my_profile(user: User = Depends(get_current_user)):
    """Any authenticated user can access their own profile."""
    return {"user_id": user.id, "username": user.username, "role": user.role.value}


@app.get("/api/admin/analytics")
async def get_analytics(user: User = Depends(RBAC(required_role=Role.ADMIN))):
    """Only admins can view analytics."""
    return {"users": 1000, "posts": 5000, "active_sessions": 42}


@app.post("/api/posts")
async def create_post(
    title: str,
    content: str,
    user: User = Depends(RBAC(required_permissions=[Permission.CREATE_POST])),
):
    """Users with create:post permission can create a post."""
    return {"message": "Post created", "title": title, "author": user.username}


@app.delete("/api/posts/{post_id}")
async def delete_post(
    post_id: str,
    user: User = Depends(require_permissions(Permission.DELETE_POST)),
):
    """Alternative syntax using require_permissions."""
    return {"message": f"Post {post_id} deleted by {user.username}"}


@app.get("/api/moderate/reports")
async def view_reports(user: User = Depends(RBAC(required_role=Role.MODERATOR))):
    """Moderators and admins can view reports."""
    return {"reports": ["report1", "report2"], "reviewed_by": user.username}
```

## Express.js RBAC Middleware

```typescript
import { Request, Response, NextFunction } from 'express';

// --- Types ---
enum Role {
  ADMIN = 'admin',
  MODERATOR = 'moderator',
  USER = 'user',
  GUEST = 'guest',
}

enum Permission {
  READ_PROFILE = 'read:profile',
  UPDATE_PROFILE = 'update:profile',
  CREATE_POST = 'create:post',
  READ_POST = 'read:post',
  DELETE_POST = 'delete:post',
  MODERATE_CONTENT = 'moderate:content',
  MANAGE_USERS = 'manage:users',
}

interface AuthUser {
  id: string;
  username: string;
  role: Role;
  customPermissions?: Permission[];
}

// Permission inheritance map
const ROLE_PERMISSIONS: Record<Role, Permission[]> = {
  [Role.ADMIN]: Object.values(Permission),
  [Role.MODERATOR]: [
    Permission.READ_PROFILE, Permission.UPDATE_PROFILE,
    Permission.CREATE_POST, Permission.READ_POST, Permission.DELETE_POST,
    Permission.MODERATE_CONTENT,
  ],
  [Role.USER]: [
    Permission.READ_PROFILE, Permission.UPDATE_PROFILE,
    Permission.CREATE_POST, Permission.READ_POST, Permission.DELETE_POST,
  ],
  [Role.GUEST]: [Permission.READ_PROFILE, Permission.READ_POST],
};

// Role hierarchy — higher index = more privileged
const ROLE_HIERARCHY: Role[] = [Role.GUEST, Role.USER, Role.MODERATOR, Role.ADMIN];

function hasRole(user: AuthUser, requiredRole: Role): boolean {
  const userIdx = ROLE_HIERARCHY.indexOf(user.role);
  const requiredIdx = ROLE_HIERARCHY.indexOf(requiredRole);
  return userIdx >= requiredIdx;
}

function hasPermission(user: AuthUser, requiredPermission: Permission): boolean {
  const basePerms = ROLE_PERMISSIONS[user.role] || [];
  const customPerms = user.customPermissions || [];
  return [...basePerms, ...customPerms].includes(requiredPermission);
}

// --- RBAC Middleware Factories ---

function requireRole(role: Role) {
  return (req: Request, res: Response, next: NextFunction) => {
    const user = (req as any).user as AuthUser | undefined;
    if (!user) {
      return res.status(401).json({ error: 'Authentication required' });
    }
    if (!hasRole(user, role)) {
      return res.status(403).json({
        error: `Insufficient role. Required: ${role}, current: ${user.role}`,
      });
    }
    next();
  };
}

function requirePermission(...permissions: Permission[]) {
  return (req: Request, res: Response, next: NextFunction) => {
    const user = (req as any).user as AuthUser | undefined;
    if (!user) {
      return res.status(401).json({ error: 'Authentication required' });
    }
    const missing = permissions.filter(p => !hasPermission(user, p));
    if (missing.length > 0) {
      return res.status(403).json({
        error: `Missing permissions: ${missing.join(', ')}`,
      });
    }
    next();
  };
}

// --- Express App ---
import express from 'express';
const app = express();

// Auth middleware (must run before RBAC)
app.use((req, res, next) => {
  const token = req.headers.authorization?.split(' ')[1];
  // In production: decode JWT, fetch user from DB
  if (token === 'admin-token') {
    (req as any).user = { id: '1', username: 'admin', role: Role.ADMIN };
  } else if (token === 'user-token') {
    (req as any).user = { id: '2', username: 'user', role: Role.USER };
  }
  next();
});

// Route examples
app.get('/api/profile', (req, res) => {
  const user = (req as any).user as AuthUser;
  res.json({ user });
});

app.get('/api/admin/analytics', requireRole(Role.ADMIN), (req, res) => {
  res.json({ users: 1000, posts: 5000 });
});

app.post('/api/posts', requirePermission(Permission.CREATE_POST), (req, res) => {
  const user = (req as any).user as AuthUser;
  res.json({ message: 'Post created', author: user.username });
});

app.delete('/api/posts/:id', requirePermission(Permission.DELETE_POST), (req, res) => {
  res.json({ message: `Post ${req.params.id} deleted` });
});

app.listen(3000, () => console.log('Server running on port 3000'));
```

## Permission Inheritance Demonstration

```python
if __name__ == "__main__":
    # Demonstrate permission inheritance
    users = [
        User(id="1", username="Alice", role=Role.ADMIN),
        User(id="2", username="Bob", role=Role.MODERATOR),
        User(id="3", username="Charlie", role=Role.USER),
        User(id="4", username="Diana", role=Role.GUEST),
    ]

    test_permissions = [
        Permission.READ_POST,
        Permission.CREATE_POST,
        Permission.MODERATE_CONTENT,
        Permission.MANAGE_USERS,
        Permission.SYSTEM_CONFIG,
    ]

    print(f"{'User':<12} {'Role':<12} {'Permissions':<60}")
    print("-" * 84)
    for user in users:
        perms = get_effective_permissions(user.role)
        perm_names = ", ".join(sorted(p.value for p in perms))
        print(f"{user.username:<12} {user.role.value:<12} {perm_names:<60}")

    print("\n--- Individual Permission Checks ---")
    for user in users:
        checks = " | ".join(
            f"{'✓' if user.has_permission(p) else '✗'} {p.value}"
            for p in test_permissions
        )
        print(f"{user.username:<12} {checks}")
```