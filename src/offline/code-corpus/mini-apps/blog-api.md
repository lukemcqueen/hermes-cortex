---
title: Blog API
description: Blog API with FastAPI + SQLAlchemy + PostgreSQL. Features posts CRUD with pagination, comments, tags, user roles (author/reader), search by title, and auto-generated OpenAPI docs.
language: python
tags: [blog, api, fastapi, sqlalchemy, crud]
---

# Blog API

A full-featured blog API built with FastAPI, SQLAlchemy, and PostgreSQL. Supports posts, comments, tags, user roles, pagination, search, and comprehensive OpenAPI documentation.

## Project Structure

```
blog-api/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── dependencies.py
│   └── routers/
│       ├── __init__.py
│       ├── posts.py
│       ├── comments.py
│       ├── tags.py
│       └── users.py
├── requirements.txt
└── docker-compose.yml
```

## Database Model

### `app/models.py`

```python
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Table, func
)
from sqlalchemy.orm import relationship
from app.database import Base

# Association table for post <-> tag many-to-many
post_tags = Table(
    "post_tags",
    Base.metadata,
    Column("post_id", Integer, ForeignKey("posts.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String(20), default="reader")  # "author" or "reader"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    posts = relationship("Post", back_populates="author")
    comments = relationship("Comment", back_populates="author")


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False, index=True)
    slug = Column(String(220), unique=True, nullable=False, index=True)
    content = Column(Text, nullable=False)
    summary = Column(String(500), default="")
    published = Column(Boolean, default=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    author = relationship("User", back_populates="posts")
    comments = relationship("Comment", back_populates="post", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary=post_tags, back_populates="posts")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    post = relationship("Post", back_populates="comments")
    author = relationship("User", back_populates="comments")


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    posts = relationship("Post", secondary=post_tags, back_populates="tags")
```

## Pydantic Schemas

### `app/schemas.py`

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


# ── Users ──

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., max_length=120)
    password: str = Field(..., min_length=8)
    role: str = Field(default="reader", pattern=r"^(author|reader)$")


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Tags ──

class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)


class TagResponse(BaseModel):
    id: int
    name: str
    post_count: int = 0

    model_config = {"from_attributes": True}


# ── Comments ──

class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


class CommentUpdate(BaseModel):
    content: Optional[str] = Field(None, min_length=1, max_length=5000)


class CommentResponse(BaseModel):
    id: int
    content: str
    post_id: int
    author_id: int
    author_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Posts ──

class PostCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    summary: Optional[str] = Field("", max_length=500)
    published: Optional[bool] = False
    tag_ids: Optional[List[int]] = []


class PostUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = Field(None, min_length=1)
    summary: Optional[str] = Field(None, max_length=500)
    published: Optional[bool] = None
    tag_ids: Optional[List[int]] = None


class PostListResponse(BaseModel):
    items: List["PostSummary"]
    total: int
    page: int
    page_size: int
    pages: int


class PostSummary(BaseModel):
    id: int
    title: str
    slug: str
    summary: Optional[str]
    published: bool
    author_id: int
    author_name: Optional[str] = None
    tags: List[TagResponse] = []
    comment_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PostDetail(BaseModel):
    id: int
    title: str
    slug: str
    content: str
    summary: Optional[str]
    published: bool
    author: Optional[UserResponse] = None
    tags: List[TagResponse] = []
    comments: List[CommentResponse] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Pagination ──

class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    search: Optional[str] = None
    tag: Optional[str] = None
    published_only: Optional[bool] = True
```

## Database Setup

### `app/database.py`

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://blog:blog@localhost:5432/blog")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

## Dependencies

### `app/dependencies.py`

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials=Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Simple token look-up for demo. Replace with real JWT in production."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # In production, decode JWT here. For demo, accept user_id as token.
    try:
        user_id = int(credentials.credentials)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_author(user: User = Depends(get_current_user)) -> User:
    """Require the user to have the 'author' role."""
    if user.role != "author":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Author privileges required",
        )
    return user
```

## Routers

### `app/routers/users.py`

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserResponse
from app.dependencies import get_current_user, require_author

router = APIRouter(prefix="/api/users", tags=["users"])


@router.post("/", response_model=UserResponse, status_code=201)
def create_user(data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user (reader by default)."""
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=409, detail="Username taken")
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=409, detail="Email taken")
    # NOTE: hash password in production
    user = User(username=data.username, email=data.email, hashed_password=data.password, role=data.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    """Get current user profile."""
    return user


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
```

### `app/routers/tags.py`

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Tag
from app.schemas import TagCreate, TagResponse

router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("/", response_model=list[TagResponse])
def list_tags(db: Session = Depends(get_db)):
    tags = db.query(Tag).all()
    result = []
    for tag in tags:
        t = TagResponse.model_validate(tag)
        t.post_count = len(tag.posts)
        result.append(t)
    return result


@router.post("/", response_model=TagResponse, status_code=201)
def create_tag(data: TagCreate, db: Session = Depends(get_db)):
    existing = db.query(Tag).filter(Tag.name == data.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Tag already exists")
    tag = Tag(name=data.name)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag
```

### `app/routers/posts.py`

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_
from slugify import slugify
import math

from app.database import get_db
from app.models import Post, Tag, User, Comment
from app.schemas import (
    PostCreate, PostUpdate, PostDetail, PostSummary, PostListResponse, PaginationParams
)
from app.dependencies import get_current_user, require_author

router = APIRouter(prefix="/api/posts", tags=["posts"])


def _post_to_summary(post: Post) -> PostSummary:
    summary = PostSummary.model_validate(post)
    summary.author_name = post.author.username if post.author else None
    summary.tags = [TagResponse.model_validate(t) for t in post.tags]
    summary.comment_count = len(post.comments)
    return summary


def _post_to_detail(post: Post) -> PostDetail:
    detail = PostDetail.model_validate(post)
    detail.author = UserResponse.model_validate(post.author) if post.author else None
    detail.tags = [TagResponse.model_validate(t) for t in post.tags]
    detail.comments = []
    for c in post.comments:
        cr = CommentResponse.model_validate(c)
        cr.author_name = c.author.username if c.author else None
        detail.comments.append(cr)
    return detail


@router.get("/", response_model=PostListResponse)
def list_posts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query(None),
    tag: str = Query(None),
    published_only: bool = Query(True),
    db: Session = Depends(get_db),
):
    """List posts with pagination, search, and tag filter."""
    query = db.query(Post).options(
        joinedload(Post.author),
        joinedload(Post.tags),
        joinedload(Post.comments),
    )

    if published_only:
        query = query.filter(Post.published == True)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(Post.title.ilike(search_term), Post.content.ilike(search_term))
        )

    if tag:
        query = query.join(Post.tags).filter(Tag.name == tag)

    total = query.count()
    pages = max(1, math.ceil(total / page_size))

    posts = (
        query.order_by(Post.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [_post_to_summary(p) for p in posts]

    return PostListResponse(items=items, total=total, page=page, page_size=page_size, pages=pages)


@router.get("/{slug}", response_model=PostDetail)
def get_post(slug: str, db: Session = Depends(get_db)):
    """Get a single post by slug."""
    post = (
        db.query(Post)
        .options(
            joinedload(Post.author),
            joinedload(Post.tags),
            joinedload(Post.comments).joinedload(Comment.author),
        )
        .filter(Post.slug == slug)
        .first()
    )
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return _post_to_detail(post)


@router.post("/", response_model=PostDetail, status_code=201)
def create_post(
    data: PostCreate,
    user: User = Depends(require_author),
    db: Session = Depends(get_db),
):
    """Create a new post (author role required)."""
    slug = slugify(data.title)
    # Ensure unique slug
    existing = db.query(Post).filter(Post.slug == slug).first()
    if existing:
        slug = f"{slug}-{int(func.now().timestamp())}"

    post = Post(
        title=data.title,
        slug=slug,
        content=data.content,
        summary=data.summary or "",
        published=data.published,
        author_id=user.id,
    )

    if data.tag_ids:
        tags = db.query(Tag).filter(Tag.id.in_(data.tag_ids)).all()
        post.tags = tags

    db.add(post)
    db.commit()
    db.refresh(post)

    # Reload with relationships
    post = (
        db.query(Post)
        .options(joinedload(Post.author), joinedload(Post.tags), joinedload(Post.comments))
        .filter(Post.id == post.id)
        .first()
    )
    return _post_to_detail(post)


@router.put("/{slug}", response_model=PostDetail)
def update_post(
    slug: str,
    data: PostUpdate,
    user: User = Depends(require_author),
    db: Session = Depends(get_db),
):
    """Update a post (author role required)."""
    post = db.query(Post).filter(Post.slug == slug).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.author_id != user.id:
        raise HTTPException(status_code=403, detail="Cannot edit another author's post")

    update_data = data.model_dump(exclude_unset=True)
    if "tag_ids" in update_data:
        tags = db.query(Tag).filter(Tag.id.in_(update_data.pop("tag_ids"))).all()
        post.tags = tags
    if "title" in update_data:
        post.title = update_data.pop("title")
        post.slug = slugify(post.title)

    for key, value in update_data.items():
        setattr(post, key, value)

    db.commit()
    db.refresh(post)

    post = (
        db.query(Post)
        .options(joinedload(Post.author), joinedload(Post.tags), joinedload(Post.comments))
        .filter(Post.id == post.id)
        .first()
    )
    return _post_to_detail(post)


@router.delete("/{slug}", status_code=204)
def delete_post(
    slug: str,
    user: User = Depends(require_author),
    db: Session = Depends(get_db),
):
    """Delete a post (author role required)."""
    post = db.query(Post).filter(Post.slug == slug).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.author_id != user.id:
        raise HTTPException(status_code=403, detail="Cannot delete another author's post")
    db.delete(post)
    db.commit()
    return None
```

### `app/routers/comments.py`

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Post, Comment, User
from app.schemas import CommentCreate, CommentUpdate, CommentResponse
from app.dependencies import get_current_user

router = APIRouter(prefix="/api/posts/{slug}/comments", tags=["comments"])


@router.get("/", response_model=list[CommentResponse])
def list_comments(slug: str, db: Session = Depends(get_db)):
    """List all comments on a post."""
    post = db.query(Post).filter(Post.slug == slug).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    comments = (
        db.query(Comment)
        .filter(Comment.post_id == post.id)
        .order_by(Comment.created_at.asc())
        .all()
    )
    result = []
    for c in comments:
        cr = CommentResponse.model_validate(c)
        cr.author_name = c.author.username if c.author else None
        result.append(cr)
    return result


@router.post("/", response_model=CommentResponse, status_code=201)
def create_comment(
    slug: str,
    data: CommentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a comment to a post."""
    post = db.query(Post).filter(Post.slug == slug).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if not post.published:
        raise HTTPException(status_code=400, detail="Cannot comment on unpublished posts")

    comment = Comment(content=data.content, post_id=post.id, author_id=user.id)
    db.add(comment)
    db.commit()
    db.refresh(comment)

    cr = CommentResponse.model_validate(comment)
    cr.author_name = user.username
    return cr


@router.put("/{comment_id}", response_model=CommentResponse)
def update_comment(
    slug: str,
    comment_id: int,
    data: CommentUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Edit your own comment."""
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.author_id != user.id:
        raise HTTPException(status_code=403, detail="Cannot edit another user's comment")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(comment, key, value)
    db.commit()
    db.refresh(comment)

    cr = CommentResponse.model_validate(comment)
    cr.author_name = user.username
    return cr


@router.delete("/{comment_id}", status_code=204)
def delete_comment(
    slug: str,
    comment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete your own comment."""
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.author_id != user.id:
        raise HTTPException(status_code=403, detail="Cannot delete another user's comment")
    db.delete(comment)
    db.commit()
    return None
```

## Main App

### `app/main.py`

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.routers import posts, comments, tags, users

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Blog API",
    description="A full-featured blog API with posts, comments, tags, and user roles. Auto-generated OpenAPI docs at /docs.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(tags.router)
app.include_router(posts.router)
app.include_router(comments.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "blog-api"}
```

## Docker Compose

### `docker-compose.yml`

```yaml
version: "3.9"

services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: blog
      POSTGRES_PASSWORD: blog
      POSTGRES_DB: blog
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://blog:blog@db:5432/blog
    depends_on:
      - db
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

volumes:
  pgdata:
```

## API Endpoints Summary

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/users/` | Register user |
| GET | `/api/users/me` | Current user |
| GET | `/api/users/:id` | Get user |
| GET | `/api/posts/` | List posts (paginated, search, filter by tag) |
| GET | `/api/posts/:slug` | Get post detail |
| POST | `/api/posts/` | Create post (author) |
| PUT | `/api/posts/:slug` | Update post (author) |
| DELETE | `/api/posts/:slug` | Delete post (author) |
| GET | `/api/posts/:slug/comments/` | List comments |
| POST | `/api/posts/:slug/comments/` | Create comment |
| PUT | `/api/posts/:slug/comments/:id` | Update comment |
| DELETE | `/api/posts/:slug/comments/:id` | Delete comment |
| GET | `/api/tags/` | List tags |
| POST | `/api/tags/` | Create tag |
| GET | `/health` | Health check |

## Key Patterns Demonstrated

- **Many-to-many** relationship (posts ↔ tags) with association table
- **One-to-many** relationships (user → posts, post → comments)
- **Pagination** with page/page_size and total count
- **Search** with `ILIKE` on title and content
- **Slug-based** URL paths with unique constraint
- **Role-based access** (author vs reader) via dependency injection
- **Cascading deletes** (deleting a post removes its comments)
- **OpenAPI docs** auto-generated at `/docs`
- **N+1 query prevention** via `joinedload`