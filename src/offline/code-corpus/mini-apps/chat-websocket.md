---
title: Real-Time Chat with WebSockets
description: Real-time chat application using FastAPI WebSockets. Features room management, message broadcast, user join/leave events, connection lifecycle handling, and a React frontend with useWebSocket.
language: python
tags: [chat, websocket, realtime, fastapi, react]
---

# Real-Time Chat with WebSockets

A real-time chat application using FastAPI's built-in WebSocket support. Demonstrates room management, message broadcasting, user presence events, and clean connection lifecycle handling.

## Architecture

```
┌─────────────┐  WebSocket (ws://)   ┌──────────────┐
│  React App  │ ◀──────────────────▶ │  FastAPI      │
│  (Client A) │                      │  WebSocket    │
│             │                      │  Server       │
│  useWebSocket│                     │               │
│  hook       │                      │  Room Manager │
└─────────────┘                      └──────┬────────┘
                                            │
┌─────────────┐                             │
│  React App  │ ◀───────────────────────────┘
│  (Client B) │     broadcast to room
└─────────────┘
```

## WebSocket Protocol

Messages are JSON with a `type` field:

**Client → Server:**
```json
{"type": "join", "room": "general", "username": "alice"}
{"type": "message", "content": "Hello everyone!"}
{"type": "leave", "room": "general"}
```

**Server → Client:**
```json
{"type": "system", "content": "alice joined the room", "timestamp": "..."}
{"type": "message", "username": "alice", "content": "Hello everyone!", "timestamp": "..."}
{"type": "user_list", "users": ["alice", "bob"]}
{"type": "error", "content": "Room not found"}
```

## Backend

### `backend/app/__init__.py`

```python
from app.main import app
from app.ws import router as ws_router

app.include_router(ws_router)
```

### `backend/app/room_manager.py`

```python
import json
import logging
from typing import Dict, List, Set
from fastapi import WebSocket
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ConnectionInfo:
    """Tracks a single WebSocket connection's metadata."""
    def __init__(self, websocket: WebSocket, username: str, room: str):
        self.websocket = websocket
        self.username = username
        self.room = room
        self.joined_at = datetime.now(timezone.utc)


class RoomManager:
    """
    Manages WebSocket rooms and broadcasts.

    Thread-safe for single-process ASGI servers (uvicorn).
    For multi-worker, use Redis pub/sub instead.
    """

    def __init__(self):
        # room_name -> set of ConnectionInfo
        self.rooms: Dict[str, Set[ConnectionInfo]] = {}
        # websocket -> ConnectionInfo (for O(1) lookup)
        self.connections: Dict[WebSocket, ConnectionInfo] = {}

    @property
    def active_connections(self) -> int:
        return len(self.connections)

    @property
    def active_rooms(self) -> List[str]:
        return list(self.rooms.keys())

    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        logger.info(f"New WebSocket connection accepted. Total: {self.active_connections}")

    async def join_room(self, websocket: WebSocket, username: str, room: str):
        """Add a user to a room and notify others."""
        info = ConnectionInfo(websocket, username, room)
        self.connections[websocket] = info

        if room not in self.rooms:
            self.rooms[room] = set()
        self.rooms[room].add(info)

        logger.info(f"{username} joined room '{room}'")

        # Notify everyone in the room (including the joiner)
        await self.broadcast_to_room(
            room,
            {
                "type": "system",
                "content": f"{username} joined the room",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        # Send updated user list
        await self.send_user_list(room)

    async def leave_room(self, websocket: WebSocket, room: str):
        """Remove a user from a room and notify others."""
        info = self.connections.pop(websocket, None)
        if not info:
            return

        username = info.username
        if room in self.rooms:
            self.rooms[room].discard(info)
            if not self.rooms[room]:
                del self.rooms[room]

        logger.info(f"{username} left room '{room}'")

        await self.broadcast_to_room(
            room,
            {
                "type": "system",
                "content": f"{username} left the room",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        await self.send_user_list(room)

    async def disconnect(self, websocket: WebSocket):
        """Handle a disconnection — remove from all rooms."""
        info = self.connections.pop(websocket, None)
        if not info:
            return

        username = info.username
        room = info.room

        if room in self.rooms:
            self.rooms[room].discard(info)
            if not self.rooms[room]:
                del self.rooms[room]

        logger.info(f"{username} disconnected from room '{room}'")

        try:
            await self.broadcast_to_room(
                room,
                {
                    "type": "system",
                    "content": f"{username} disconnected",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            await self.send_user_list(room)
        except Exception:
            pass  # Room may already be dead

    async def broadcast_to_room(self, room: str, message: dict):
        """Send a message to all connected clients in a room."""
        if room not in self.rooms:
            return

        payload = json.dumps(message, default=str)
        disconnected: List[WebSocket] = []

        for info in self.rooms[room]:
            try:
                await info.websocket.send_text(payload)
            except Exception as e:
                logger.warning(f"Failed to send to {info.username}: {e}")
                disconnected.append(info.websocket)

        # Clean up disconnected clients
        for ws in disconnected:
            await self.disconnect(ws)

    async def send_to(self, websocket: WebSocket, message: dict):
        """Send a message to a specific client."""
        try:
            await websocket.send_text(json.dumps(message, default=str))
        except Exception as e:
            logger.error(f"Failed to send to client: {e}")

    async def send_user_list(self, room: str):
        """Broadcast the current user list for a room."""
        if room not in self.rooms:
            return

        users = sorted([info.username for info in self.rooms[room]])
        await self.broadcast_to_room(
            room,
            {
                "type": "user_list",
                "users": users,
                "room": room,
            },
        )

    def get_room_users(self, room: str) -> List[str]:
        """Get usernames in a room (no I/O)."""
        if room not in self.rooms:
            return []
        return sorted([info.username for info in self.rooms[room]])


# Singleton
manager = RoomManager()
```

### `backend/app/ws.py`

```python
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Optional

from app.room_manager import manager
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/{room}")
async def chat_websocket(websocket: WebSocket, room: str, username: Optional[str] = None):
    """
    WebSocket endpoint for a chat room.

    Query params:
      - username (optional): can also be sent as first JSON message
    """
    await manager.connect(websocket)
    current_username = username or "anonymous"

    # If username wasn't in the path, wait for a join message
    if not username:
        try:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "join" and msg.get("username"):
                current_username = msg["username"]
                room = msg.get("room", room)
            else:
                await manager.send_to(websocket, {"type": "error", "content": "First message must be a join with username"})
                await websocket.close()
                return
        except Exception:
            await websocket.close()
            return

    await manager.join_room(websocket, current_username, room)

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type", "message")

            if msg_type == "message":
                content = message.get("content", "").strip()
                if not content:
                    continue

                await manager.broadcast_to_room(
                    room,
                    {
                        "type": "message",
                        "username": current_username,
                        "content": content,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )

            elif msg_type == "join":
                new_room = message.get("room", room)
                if new_room != room:
                    # Move to a different room
                    await manager.leave_room(websocket, room)
                    room = new_room
                    current_username = message.get("username", current_username)
                    await manager.join_room(websocket, current_username, room)

            elif msg_type == "typing":
                await manager.broadcast_to_room(
                    room,
                    {
                        "type": "typing",
                        "username": current_username,
                        "is_typing": message.get("is_typing", False),
                    },
                )

            elif msg_type == "leave":
                await manager.leave_room(websocket, room)
                break

            elif msg_type == "ping":
                await manager.send_to(websocket, {"type": "pong"})

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {current_username} in '{room}'")
    except Exception as e:
        logger.error(f"WebSocket error for {current_username}: {e}")
    finally:
        await manager.disconnect(websocket)


@router.get("/ws/rooms")
async def list_rooms():
    """List active rooms and user counts."""
    return {
        "rooms": {
            room: {
                "user_count": len(connections),
                "users": manager.get_room_users(room),
            }
            for room, connections in manager.rooms.items()
        },
        "total_connections": manager.active_connections,
    }
```

### `backend/app/main.py`

```python
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ws import router as ws_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Chat WebSocket API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ws_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "chat-ws"}
```

### `backend/requirements.txt`

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
websockets==13.0
```

### `backend/Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## React Frontend

### `frontend/src/hooks/useWebSocket.ts`

```typescript
import { useEffect, useRef, useCallback, useState } from "react";

type MessageHandler = (data: any) => void;

interface UseWebSocketOptions {
  url: string;
  onMessage?: MessageHandler;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
  reconnectInterval?: number;  // ms between reconnection attempts
  maxReconnects?: number;
}

interface UseWebSocketReturn {
  send: (data: any) => void;
  close: () => void;
  isConnected: boolean;
  reconnect: () => void;
  connectionAttempts: number;
}

export function useWebSocket({
  url,
  onMessage,
  onOpen,
  onClose,
  onError,
  reconnectInterval = 3000,
  maxReconnects = 10,
}: UseWebSocketOptions): UseWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout>>();
  const [isConnected, setIsConnected] = useState(false);
  const [connectionAttempts, setConnectionAttempts] = useState(0);
  const isUnmountedRef = useRef(false);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    wsRef.current = new WebSocket(url);

    wsRef.current.onopen = () => {
      console.log(`WebSocket connected to ${url}`);
      setIsConnected(true);
      reconnectAttemptsRef.current = 0;
      setConnectionAttempts(0);
      onOpen?.();
    };

    wsRef.current.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage?.(data);
      } catch {
        onMessage?.(event.data);
      }
    };

    wsRef.current.onerror = (error) => {
      console.error("WebSocket error:", error);
      onError?.(error);
    };

    wsRef.current.onclose = (event) => {
      console.log(`WebSocket closed: code=${event.code}, reason=${event.reason}`);
      setIsConnected(false);
      onClose?.();

      // Auto-reconnect (skip if clean close or max reached)
      if (
        !isUnmountedRef.current &&
        event.code !== 1000 &&
        reconnectAttemptsRef.current < maxReconnects
      ) {
        reconnectAttemptsRef.current += 1;
        setConnectionAttempts(reconnectAttemptsRef.current);
        console.log(
          `Reconnecting in ${reconnectInterval}ms (attempt ${reconnectAttemptsRef.current}/${maxReconnects})...`
        );
        reconnectTimerRef.current = setTimeout(connect, reconnectInterval);
      }
    };
  }, [url, onMessage, onOpen, onClose, onError, reconnectInterval, maxReconnects]);

  useEffect(() => {
    isUnmountedRef.current = false;
    connect();

    return () => {
      isUnmountedRef.current = true;
      clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close(1000, "Component unmounted");
    };
  }, [connect]);

  const send = useCallback((data: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    } else {
      console.warn("WebSocket not connected, cannot send message");
    }
  }, []);

  const close = useCallback(() => {
    clearTimeout(reconnectTimerRef.current);
    reconnectAttemptsRef.current = maxReconnects; // Prevent reconnect
    wsRef.current?.close(1000, "User disconnected");
  }, [maxReconnects]);

  const reconnect = useCallback(() => {
    reconnectAttemptsRef.current = 0;
    setConnectionAttempts(0);
    wsRef.current?.close();
    // connect() will be called by onclose handler
  }, []);

  return { send, close, isConnected, reconnect, connectionAttempts };
}
```

### `frontend/src/components/ChatRoom.tsx`

```typescript
import React, { useState, useRef, useEffect } from "react";
import { useWebSocket } from "../hooks/useWebSocket";

interface ChatMessage {
  type: "message" | "system" | "user_list";
  username?: string;
  content?: string;
  users?: string[];
  timestamp?: string;
  is_typing?: boolean;
}

interface Props {
  room: string;
  username: string;
  onLeave: () => void;
}

export function ChatRoom({ room, username, onLeave }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [users, setUsers] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [typingUsers, setTypingUsers] = useState<Set<string>>(new Set());
  const typingTimeoutRef = useRef<ReturnType<typeof setTimeout>>();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Build WebSocket URL with room and username
  const wsUrl = `${import.meta.env.VITE_WS_URL || "ws://localhost:8000"}/ws/${room}?username=${encodeURIComponent(username)}`;

  const handleMessage = (data: ChatMessage) => {
    switch (data.type) {
      case "message":
        setMessages((prev) => [...prev, data]);
        // Clear typing indicator from this user
        setTypingUsers((prev) => {
          const next = new Set(prev);
          next.delete(data.username!);
          return next;
        });
        break;

      case "system":
        setMessages((prev) => [...prev, data]);
        break;

      case "user_list":
        setUsers(data.users || []);
        break;

      case "typing":
        if (data.is_typing) {
          setTypingUsers((prev) => new Set(prev).add(data.username!));
        } else {
          setTypingUsers((prev) => {
            const next = new Set(prev);
            next.delete(data.username!);
            return next;
          });
        }
        break;
    }
  };

  const { send, isConnected, connectionAttempts } = useWebSocket({
    url: wsUrl,
    onMessage: handleMessage,
    reconnectInterval: 3000,
    maxReconnects: 10,
  });

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Focus input on connect
  useEffect(() => {
    if (isConnected) {
      inputRef.current?.focus();
    }
  }, [isConnected]);

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || !isConnected) return;

    send({ type: "message", content: input.trim() });
    setInput("");

    // Clear typing indicator
    clearTimeout(typingTimeoutRef.current);
    send({ type: "typing", is_typing: false });
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setInput(e.target.value);

    // Send typing indicator
    if (isConnected) {
      send({ type: "typing", is_typing: true });
      clearTimeout(typingTimeoutRef.current);
      typingTimeoutRef.current = setTimeout(() => {
        send({ type: "typing", is_typing: false });
      }, 2000);
    }
  };

  const formatTime = (timestamp?: string) => {
    if (!timestamp) return "";
    try {
      const d = new Date(timestamp);
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch {
      return "";
    }
  };

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <div>
          <strong># {room}</strong>
          <span style={styles.status}>
            {isConnected ? "🟢 Connected" : `🔴 Disconnected${connectionAttempts > 0 ? ` (reconnect #${connectionAttempts})` : ""}`}
          </span>
        </div>
        <div>
          <span style={styles.userCount}>{users.length} users</span>
          <button onClick={onLeave} style={styles.leaveBtn}>Leave</button>
        </div>
      </div>

      {/* User list sidebar */}
      <div style={styles.layout}>
        <div style={styles.sidebar}>
          <strong>Online</strong>
          {users.map((u) => (
            <div key={u} style={{ ...styles.userItem, fontWeight: u === username ? "bold" : "normal" }}>
              {u === username ? "👤" : "👥"} {u}
            </div>
          ))}
        </div>

        {/* Messages */}
        <div style={styles.chatArea}>
          <div style={styles.messages}>
            {messages.length === 0 && (
              <div style={styles.emptyState}>
                No messages yet. Say hello!
              </div>
            )}
            {messages.map((msg, i) => (
              <div
                key={i}
                style={{
                  ...styles.message,
                  textAlign: msg.type === "system" ? "center" : "left",
                  opacity: msg.type === "system" ? 0.7 : 1,
                }}
              >
                {msg.type === "system" ? (
                  <span style={styles.systemMsg}>
                    {msg.content} <small>{formatTime(msg.timestamp)}</small>
                  </span>
                ) : (
                  <>
                    <strong style={styles.username}>{msg.username}</strong>
                    <span style={styles.msgContent}>{msg.content}</span>
                    <small style={styles.time}>{formatTime(msg.timestamp)}</small>
                  </>
                )}
              </div>
            ))}
            {typingUsers.size > 0 && (
              <div style={{ ...styles.message, fontStyle: "italic", opacity: 0.6 }}>
                {Array.from(typingUsers).join(", ")}{" "}
                {typingUsers.size === 1 ? "is" : "are"} typing...
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <form onSubmit={handleSend} style={styles.inputBar}>
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={handleInputChange}
              placeholder={isConnected ? "Type a message..." : "Reconnecting..."}
              disabled={!isConnected}
              style={styles.input}
              maxLength={1000}
            />
            <button
              type="submit"
              disabled={!isConnected || !input.trim()}
              style={styles.sendBtn}
            >
              Send
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: "flex",
    flexDirection: "column",
    height: "80vh",
    maxWidth: "900px",
    margin: "0 auto",
    border: "1px solid #ccc",
    borderRadius: "8px",
    overflow: "hidden",
    fontFamily: "system-ui, sans-serif",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "0.75rem 1rem",
    borderBottom: "1px solid #ddd",
    background: "#f5f5f5",
  },
  status: {
    marginLeft: "0.5rem",
    fontSize: "0.8rem",
  },
  userCount: {
    marginRight: "0.5rem",
    fontSize: "0.85rem",
    color: "#666",
  },
  leaveBtn: {
    padding: "0.25rem 0.75rem",
    background: "#e74c3c",
    color: "white",
    border: "none",
    borderRadius: "4px",
    cursor: "pointer",
  },
  layout: {
    display: "flex",
    flex: 1,
    overflow: "hidden",
  },
  sidebar: {
    width: "150px",
    borderRight: "1px solid #ddd",
    padding: "0.5rem",
    background: "#fafafa",
    overflowY: "auto",
  },
  userItem: {
    padding: "0.25rem 0",
    fontSize: "0.85rem",
  },
  chatArea: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
  },
  messages: {
    flex: 1,
    overflowY: "auto",
    padding: "0.5rem 1rem",
  },
  emptyState: {
    textAlign: "center",
    color: "#999",
    marginTop: "2rem",
  },
  message: {
    padding: "0.25rem 0",
    lineHeight: 1.5,
  },
  systemMsg: {
    fontSize: "0.85rem",
    color: "#888",
  },
  username: {
    marginRight: "0.5rem",
    color: "#2c3e50",
  },
  msgContent: {
    marginRight: "0.5rem",
  },
  time: {
    fontSize: "0.75rem",
    color: "#aaa",
    marginLeft: "0.25rem",
  },
  inputBar: {
    display: "flex",
    padding: "0.5rem",
    borderTop: "1px solid #ddd",
    background: "#fff",
  },
  input: {
    flex: 1,
    padding: "0.5rem",
    border: "1px solid #ccc",
    borderRadius: "4px",
    marginRight: "0.5rem",
    fontSize: "1rem",
  },
  sendBtn: {
    padding: "0.5rem 1rem",
    background: "#3498db",
    color: "white",
    border: "none",
    borderRadius: "4px",
    cursor: "pointer",
    fontSize: "1rem",
  },
};
```

### `frontend/src/components/JoinForm.tsx`

```typescript
import React, { useState } from "react";

interface Props {
  onJoin: (room: string, username: string) => void;
}

export function JoinForm({ onJoin }: Props) {
  const [room, setRoom] = useState("general");
  const [username, setUsername] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!room.trim() || !username.trim()) return;
    onJoin(room.trim(), username.trim());
  };

  return (
    <form onSubmit={handleSubmit} style={{ maxWidth: "400px", margin: "2rem auto" }}>
      <h2>Join a Chat Room</h2>
      <div style={{ marginBottom: "1rem" }}>
        <label>Room</label>
        <input
          type="text"
          value={room}
          onChange={(e) => setRoom(e.target.value)}
          placeholder="e.g. general"
          required
          style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
        />
      </div>
      <div style={{ marginBottom: "1rem" }}>
        <label>Username</label>
        <input
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="Your display name"
          required
          minLength={2}
          style={{ width: "100%", padding: "0.5rem", marginTop: "0.25rem" }}
        />
      </div>
      <button
        type="submit"
        disabled={!room.trim() || !username.trim()}
        style={{
          padding: "0.5rem 1rem",
          background: "#2ecc71",
          color: "white",
          border: "none",
          borderRadius: "4px",
          cursor: "pointer",
          fontSize: "1rem",
        }}
      >
        Join Chat
      </button>
    </form>
  );
}
```

### `frontend/src/App.tsx`

```typescript
import React, { useState } from "react";
import { JoinForm } from "./components/JoinForm";
import { ChatRoom } from "./components/ChatRoom";

type View =
  | { type: "join" }
  | { type: "chat"; room: string; username: string };

function App() {
  const [view, setView] = useState<View>({ type: "join" });

  if (view.type === "join") {
    return (
      <div>
        <JoinForm
          onJoin={(room, username) => setView({ type: "chat", room, username })}
        />
      </div>
    );
  }

  return (
    <ChatRoom
      room={view.room}
      username={view.username}
      onLeave={() => setView({ type: "join" })}
    />
  );
}

export default App;
```

### `frontend/package.json`

```json
{
  "name": "chat-frontend",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "typescript": "^5.5.0",
    "vite": "^5.4.0"
  }
}
```

## Running

```bash
# Backend
pip install -r backend/requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev

# Open http://localhost:5173 in two browser tabs to test chat
```

## Key Patterns Demonstrated

- **FastAPI WebSocket endpoint** with `WebSocket` and `WebSocketDisconnect`
- **Room manager** — in-memory singleton for room state management
- **Broadcast** — send messages to all room members
- **Join/leave events** — system messages and user list updates
- **Connection lifecycle** — `connect`, `disconnect`, error handling
- **Custom `useWebSocket` hook** — with auto-reconnect logic
- **Typing indicators** — debounced typing events
- **User presence** — live user list per room
- **Ping/pong** — keepalive mechanism
- **Room switching** — move between rooms without reconnecting