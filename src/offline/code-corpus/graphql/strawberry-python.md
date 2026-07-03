---
language: python
tags: [graphql, strawberry, python, api]
title: Strawberry GraphQL (Python)
description: Schema definition with decorators, resolvers, mutations, dataloader for N+1, integration with FastAPI
source: pattern
---

# Strawberry GraphQL (Python)

## Setup

```python
# pip install strawberry-graphql[fastapi]
import strawberry
from typing import List, Optional
from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter
```

## Schema Definition with Decorators

```python
import strawberry
from datetime import datetime
from typing import Optional


@strawberry.type
class User:
    id: strawberry.ID
    email: str
    name: str
    role: str
    created_at: str


@strawberry.type
class Post:
    id: strawberry.ID
    title: str
    content: str
    published: bool
    author_id: str
    created_at: str
    updated_at: str

    # Resolver for related field (avoids N+1 with DataLoader)
    @strawberry.field
    async def author(self) -> User:
        return await get_user_by_id(self.author_id)


@strawberry.input
class CreatePostInput:
    title: str
    content: str
    published: bool = False


@strawberry.input
class UpdatePostInput:
    title: Optional[str] = None
    content: Optional[str] = None
    published: Optional[bool] = None


@strawberry.input
class PaginationInput:
    page: int = 1
    limit: int = 10


@strawberry.type
class AuthPayload:
    token: str
    user: User


@strawberry.enum
class SortOrder:
    ASC = "asc"
    DESC = "desc"
```

## Resolvers & Query / Mutation Classes

```python
from strawberry.types import Info


# --- Mock Database ---
USERS_DB = [
    {"id": "1", "email": "alice@example.com", "name": "Alice", "role": "ADMIN", "created_at": "2024-01-01T00:00:00Z"},
    {"id": "2", "email": "bob@example.com", "name": "Bob", "role": "USER", "created_at": "2024-01-02T00:00:00Z"},
]

POSTS_DB = [
    {"id": "1", "title": "Hello World", "content": "First post!", "published": True, "author_id": "1",
     "created_at": "2024-01-03T00:00:00Z", "updated_at": "2024-01-03T00:00:00Z"},
    {"id": "2", "title": "GraphQL Rocks", "content": "Second post!", "published": True, "author_id": "2",
     "created_at": "2024-01-04T00:00:00Z", "updated_at": "2024-01-04T00:00:00Z"},
]

LAST_ID = {"user": 2, "post": 2}


# --- Mock async DB functions ---
async def get_user_by_id(user_id: str) -> Optional[User]:
    for u in USERS_DB:
        if u["id"] == user_id:
            return User(id=strawberry.ID(u["id"]), **{k: v for k, v in u.items() if k != "id"})
    return None


async def get_all_users() -> List[User]:
    return [User(id=strawberry.ID(u["id"]), **{k: v for k, v in u.items() if k != "id"}) for u in USERS_DB]


async def get_post_by_id(post_id: str) -> Optional[Post]:
    for p in POSTS_DB:
        if p["id"] == post_id:
            return Post(id=strawberry.ID(p["id"]), **{k: v for k, v in p.items() if k != "id"})
    return None


async def get_posts_by_author(author_id: str) -> List[Post]:
    return [Post(id=strawberry.ID(p["id"]), **{k: v for k, v in p.items() if k != "id"})
            for p in POSTS_DB if p["author_id"] == author_id]


async def create_post(input: CreatePostInput, author_id: str) -> Post:
    global LAST_ID
    LAST_ID["post"] += 1
    now = datetime.utcnow().isoformat() + "Z"
    post = {
        "id": str(LAST_ID["post"]),
        "title": input.title,
        "content": input.content,
        "published": input.published,
        "author_id": author_id,
        "created_at": now,
        "updated_at": now,
    }
    POSTS_DB.append(post)
    return Post(id=strawberry.ID(post["id"]), **{k: v for k, v in post.items() if k != "id"})


# --- Context type ---
@strawberry.type
class Context:
    request: object
    user: Optional[User] = None
    db: object = None
```

## Query Class

```python
@strawberry.type
class Query:
    @strawberry.field
    async def user(self, id: strawberry.ID) -> Optional[User]:
        """Get a user by ID."""
        return await get_user_by_id(str(id))

    @strawberry.field
    async def me(self, info: Info) -> Optional[User]:
        """Get the currently authenticated user."""
        user = info.context.user
        if not user:
            raise PermissionError("Authentication required")
        return user

    @strawberry.field
    async def posts(
        self,
        pagination: Optional[PaginationInput] = None,
    ) -> List[Post]:
        """List posts with pagination."""
        page = pagination.page if pagination else 1
        limit = pagination.limit if pagination else 10
        start = (page - 1) * limit
        end = start + limit
        posts = [Post(id=strawberry.ID(p["id"]), **{k: v for k, v in p.items() if k != "id"}) for p in POSTS_DB]
        return posts[start:end]

    @strawberry.field
    async def post(self, id: strawberry.ID) -> Optional[Post]:
        """Get a single post by ID."""
        return await get_post_by_id(str(id))

    @strawberry.field
    async def search_posts(self, query: str) -> List[Post]:
        """Search posts by title."""
        results = [p for p in POSTS_DB if query.lower() in p["title"].lower()]
        return [Post(id=strawberry.ID(p["id"]), **{k: v for k, v in p.items() if k != "id"}) for p in results]
```

## Mutation Class

```python
@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_post(self, input: CreatePostInput, info: Info) -> Post:
        """Create a new post (authentication required)."""
        if not info.context.user:
            raise PermissionError("Authentication required")
        return await create_post(input, info.context.user.id)

    @strawberry.mutation
    async def update_post(
        self, id: strawberry.ID, input: UpdatePostInput, info: Info
    ) -> Optional[Post]:
        """Update a post (author or admin only)."""
        if not info.context.user:
            raise PermissionError("Authentication required")

        post = await get_post_by_id(str(id))
        if not post:
            return None

        # Check authorization
        if post.author_id != info.context.user.id and info.context.user.role != "ADMIN":
            raise PermissionError("You can only edit your own posts")

        # Update fields
        for p in POSTS_DB:
            if p["id"] == str(id):
                if input.title is not None:
                    p["title"] = input.title
                if input.content is not None:
                    p["content"] = input.content
                if input.published is not None:
                    p["published"] = input.published
                p["updated_at"] = datetime.utcnow().isoformat() + "Z"
                break

        return await get_post_by_id(str(id))

    @strawberry.mutation
    async def delete_post(self, id: strawberry.ID, info: Info) -> bool:
        """Delete a post (author or admin only)."""
        if not info.context.user:
            raise PermissionError("Authentication required")

        post = await get_post_by_id(str(id))
        if not post:
            return False

        if post.author_id != info.context.user.id and info.context.user.role != "ADMIN":
            raise PermissionError("You can only delete your own posts")

        global POSTS_DB
        POSTS_DB = [p for p in POSTS_DB if p["id"] != str(id)]
        return True

    @strawberry.mutation
    async def login(self, email: str, password: str) -> AuthPayload:
        """Login and return a JWT token."""
        # In production, verify against hashed passwords in DB
        user = await get_user_by_email(email)
        if not user or password != "secret":
            raise ValueError("Invalid credentials")

        # Generate JWT
        import jwt
        token = jwt.encode(
            {"user_id": user.id, "role": user.role},
            "your-secret-key",
            algorithm="HS256",
        )
        return AuthPayload(token=token, user=user)


async def get_user_by_email(email: str) -> Optional[User]:
    for u in USERS_DB:
        if u["email"] == email:
            return User(id=strawberry.ID(u["id"]), **{k: v for k, v in u.items() if k != "id"})
    return None
```

## DataLoader for N+1 Prevention

```python
from strawberry.dataloader import DataLoader
from collections import defaultdict


# --- Batch loading function ---
async def load_users_batch(user_ids: List[str]) -> List[Optional[User]]:
    """
    Batch load users. Strawberry's DataLoader calls this with
    a list of keys and expects results in the same order.
    """
    print(f"Batch loading users: {user_ids}")
    user_map = {u["id"]: u for u in USERS_DB if u["id"] in user_ids}
    return [
        User(id=strawberry.ID(u["id"]), **{k: v for k, v in u.items() if k != "id"})
        if u else None
        for u in (user_map.get(uid) for uid in user_ids)
    ]


async def load_posts_batch(post_ids: List[str]) -> List[Optional[Post]]:
    """Batch load posts."""
    print(f"Batch loading posts: {post_ids}")
    post_map = {p["id"]: p for p in POSTS_DB if p["id"] in post_ids}
    return [
        Post(id=strawberry.ID(p["id"]), **{k: v for k, v in p.items() if k != "id"})
        if p else None
        for p in (post_map.get(pid) for pid in post_ids)
    ]


# --- Create loaders ---
user_loader = DataLoader(load_fn=load_users_batch)
post_loader = DataLoader(load_fn=load_posts_batch)


# --- Updated Post type using DataLoader ---
@strawberry.type
class PostWithLoader:
    id: strawberry.ID
    title: str
    content: str
    published: bool
    author_id: str
    created_at: str
    updated_at: str

    @strawberry.field
    async def author(self) -> Optional[User]:
        """Resolve author using DataLoader (batches N+1 queries)."""
        return await user_loader.load(self.author_id)


@strawberry.type
class QueryWithLoader:
    @strawberry.field
    async def posts_with_loader(self) -> List[PostWithLoader]:
        """Posts with dataloader-backed author resolution."""
        return [
            PostWithLoader(
                id=strawberry.ID(p["id"]),
                title=p["title"],
                content=p["content"],
                published=p["published"],
                author_id=p["author_id"],
                created_at=p["created_at"],
                updated_at=p["updated_at"],
            )
            for p in POSTS_DB
        ]
```

## Integration with FastAPI

```python
from fastapi import FastAPI, Request
from strawberry.fastapi import GraphQLRouter
from strawberry.types import Info as StrawberryInfo
import jwt

# Schema
schema = strawberry.Schema(query=Query, mutation=Mutation)

# Or with DataLoader queries:
# schema = strawberry.Schema(query=QueryWithLoader, mutation=Mutation)


# Context dependency
async def get_context(request: Request, response=None):
    """Build GraphQL context with authentication."""
    user = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = jwt.decode(token, "your-secret-key", algorithms=["HS256"])
            user = await get_user_by_id(payload.get("user_id"))
        except jwt.PyJWTError:
            pass

    return Context(request=request, user=user)


# GraphQL router
graphql_app = GraphQLRouter(
    schema,
    context_getter=get_context,
    graphiql=True,  # Enable GraphiQL IDE in development
)

# FastAPI app
app = FastAPI()
app.include_router(graphql_app, prefix="/graphql")


@app.get("/")
async def root():
    return {"message": "Strawberry GraphQL running at /graphql"}


# Optional: Add a health check
@app.get("/health")
async def health():
    return {"status": "ok", "graphql_endpoint": "/graphql"}


# Run with: uvicorn main:app --reload
```

## Example Queries

```python
"""
# GraphQL queries for testing:

# Query with variables
query GetUser($userId: ID!) {
  user(id: $userId) {
    id
    name
    email
    posts {
      title
      content
    }
  }
}
# Variables: {"userId": "1"}

# Create a post
mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    id
    title
    published
    author {
      name
    }
  }
}
# Variables: {"input": {"title": "Test", "content": "Hello", "published": true}}

# Login
mutation Login($email: String!, $password: String!) {
  login(email: $email, password: $password) {
    token
    user {
      id
      name
      role
    }
  }
}
# Variables: {"email": "alice@example.com", "password": "secret"}

# Using the Auth header:
# { "Authorization": "Bearer <token>" }
"""
```