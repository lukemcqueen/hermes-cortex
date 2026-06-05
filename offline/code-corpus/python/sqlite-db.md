---
language: python
tags: [db, sql]
title: SQLite Database
description: SQLite operations: create, insert, query, update, delete with context managers.
source: pattern
---

```python
import sqlite3
from contextlib import closing

def init_db(path):
    with closing(sqlite3.connect(path)) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            value REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        conn.commit()

def insert_item(path, name, value):
    with closing(sqlite3.connect(path)) as conn:
        cur = conn.execute(
            'INSERT INTO items (name, value) VALUES (?, ?)',
            (name, value)
        )
        conn.commit()
        return cur.lastrowid

def query_items(path, min_value=None):
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        if min_value is not None:
            cur = conn.execute(
                'SELECT * FROM items WHERE value >= ? ORDER BY value DESC',
                (min_value,)
            )
        else:
            cur = conn.execute('SELECT * FROM items ORDER BY created_at DESC')
        return [dict(row) for row in cur.fetchall()]

def update_item(path, item_id, name=None, value=None):
    with closing(sqlite3.connect(path)) as conn:
        if name is not None:
            conn.execute('UPDATE items SET name = ? WHERE id = ?', (name, item_id))
        if value is not None:
            conn.execute('UPDATE items SET value = ? WHERE id = ?', (value, item_id))
        conn.commit()

def delete_item(path, item_id):
    with closing(sqlite3.connect(path)) as conn:
        conn.execute('DELETE FROM items WHERE id = ?', (item_id,))
        conn.commit()

```
