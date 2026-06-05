"""Core snippets — the original 29 bundled with the initial release.
Python (17), JavaScript (2), Go (2), Rust (1), Shell (3), Generic (3).
"""

SNIPPETS = [
    # ═══════════════════════════════════════════════════════════
    #  PYTHON
    # ═══════════════════════════════════════════════════════════

    # ── Algorithms ──
    ("python/binary-search.md", "python", ["algorithm", "search"],
     "Binary Search", "Binary search on a sorted array. O(log n). Returns index or -1.", "textbook",
     """def binary_search(arr, target):
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1"""),

    ("python/breadth-first-search.md", "python", ["algorithm", "graph"],
     "Breadth-First Search", "BFS on a graph using a deque. Returns shortest path distance.", "textbook",
     """from collections import deque

def bfs(graph, start, target):
    visited = {start}
    queue = deque([(start, 0)])
    while queue:
        node, dist = queue.popleft()
        if node == target:
            return dist
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, dist + 1))
    return -1"""),

    ("python/dijkstra.md", "python", ["algorithm", "graph", "pathfinding"],
     "Dijkstra's Shortest Path", "Dijkstra using heapq. Returns shortest distances from source.", "textbook",
     """import heapq

def dijkstra(graph, start):
    distances = {node: float('inf') for node in graph}
    distances[start] = 0
    pq = [(0, start)]
    while pq:
        dist, node = heapq.heappop(pq)
        if dist > distances[node]:
            continue
        for neighbor, weight in graph[node].items():
            new_dist = dist + weight
            if new_dist < distances[neighbor]:
                distances[neighbor] = new_dist
                heapq.heappush(pq, (new_dist, neighbor))
    return distances"""),

    ("python/merge-sort.md", "python", ["algorithm", "sorting"],
     "Merge Sort", "Stable O(n log n) divide-and-conquer sort.", "textbook",
     """def merge_sort(arr):
    if len(arr) <= 1:
        return arr
    mid = len(arr) // 2
    left = merge_sort(arr[:mid])
    right = merge_sort(arr[mid:])
    return _merge(left, right)

def _merge(left, right):
    result = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    result.extend(left[i:])
    result.extend(right[j:])
    return result"""),

    # ── Data Structures ──
    ("python/lru-cache.md", "python", ["data-structure", "cache"],
     "LRU Cache", "Least-Recently-Used cache with O(1) get/put using OrderedDict.", "pattern",
     """from collections import OrderedDict

class LRUCache:
    def __init__(self, capacity):
        self.cache = OrderedDict()
        self.capacity = capacity

    def get(self, key):
        if key not in self.cache:
            return -1
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key, value):
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)"""),

    ("python/linked-list.md", "python", ["data-structure"],
     "Singly Linked List", "Basic linked list with push, pop, reverse, and traversal.", "textbook",
     """class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next

class LinkedList:
    def __init__(self):
        self.head = None

    def push(self, val):
        node = ListNode(val, self.head)
        self.head = node

    def pop(self):
        if not self.head:
            raise IndexError('empty list')
        val = self.head.val
        self.head = self.head.next
        return val

    def reverse(self):
        prev, curr = None, self.head
        while curr:
            nxt = curr.next
            curr.next = prev
            prev, curr = curr, nxt
        self.head = prev

    def to_list(self):
        result = []
        curr = self.head
        while curr:
            result.append(curr.val)
            curr = curr.next
        return result"""),

    # ── I/O ──
    ("python/read-write-file.md", "python", ["io", "file"],
     "Read/Write File", "Read and write text files safely with context managers.", "pattern",
     """# Read entire file
with open('file.txt', 'r') as f:
    content = f.read()

# Read line by line
with open('file.txt', 'r') as f:
    for line in f:
        print(line.strip())

# Write file
with open('file.txt', 'w') as f:
    f.write('hello\\n')

# Append
with open('file.txt', 'a') as f:
    f.write('more data\\n')

# Read JSON
import json
with open('data.json') as f:
    data = json.load(f)

# Write JSON
with open('data.json', 'w') as f:
    json.dump(data, f, indent=2)"""),

    ("python/argparse-cli.md", "python", ["cli", "sys"],
     "Argparse CLI", "Build a command-line interface with argparse: flags, positional args, subcommands.", "pattern",
     """import argparse

def main():
    parser = argparse.ArgumentParser(description='Tool description')
    parser.add_argument('input', help='Input file path')
    parser.add_argument('-o', '--output', default='out.txt', help='Output file')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--limit', type=int, default=10, help='Max results')

    args = parser.parse_args()

    if args.verbose:
        print(f'Processing {args.input} -> {args.output}')

    # Your logic here
    with open(args.input) as f:
        data = f.read()

    print(f'Done. Read {len(data)} bytes.')

if __name__ == '__main__':
    main()"""),

    # ── Web ──
    ("python/flask-api.md", "python", ["web", "api"],
     "Flask REST API", "Minimal Flask REST API with JSON endpoints and error handling.", "framework",
     """from flask import Flask, request, jsonify

app = Flask(__name__)

# In-memory store for demo
items = {}

@app.route('/api/items', methods=['GET'])
def list_items():
    return jsonify(list(items.values()))

@app.route('/api/items/<int:item_id>', methods=['GET'])
def get_item(item_id):
    item = items.get(item_id)
    if not item:
        return jsonify({'error': 'not found'}), 404
    return jsonify(item)

@app.route('/api/items', methods=['POST'])
def create_item():
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({'error': 'name required'}), 400
    item_id = max(items.keys(), default=0) + 1
    items[item_id] = {'id': item_id, 'name': data['name']}
    return jsonify(items[item_id]), 201

@app.route('/api/items/<int:item_id>', methods=['DELETE'])
def delete_item(item_id):
    if item_id not in items:
        return jsonify({'error': 'not found'}), 404
    del items[item_id]
    return '', 204

if __name__ == '__main__':
    app.run(debug=True)"""),

    ("python/requests-pattern.md", "python", ["web", "net", "api"],
     "HTTP Requests with urllib", "Make HTTP requests using Python stdlib. No external deps needed.", "pattern",
     """import urllib.request
import urllib.parse
import json

# GET
with urllib.request.urlopen('https://api.example.com/data') as resp:
    data = json.loads(resp.read().decode())

# GET with params
params = urllib.parse.urlencode({'q': 'search term', 'page': 1})
with urllib.request.urlopen(f'https://api.example.com/search?{params}') as resp:
    data = json.loads(resp.read().decode())

# POST with JSON body
body = json.dumps({'name': 'test'}).encode()
req = urllib.request.Request(
    'https://api.example.com/items',
    data=body,
    headers={'Content-Type': 'application/json'},
    method='POST'
)
with urllib.request.urlopen(req) as resp:
    result = json.loads(resp.read().decode())

# With timeout
try:
    with urllib.request.urlopen('https://example.com', timeout=10) as resp:
        print(resp.read()[:100])
except urllib.error.URLError as e:
    print(f'Request failed: {e}')"""),

    ("python/sqlite-db.md", "python", ["db", "sql"],
     "SQLite Database", "SQLite operations: create, insert, query, update, delete with context managers.", "pattern",
     """import sqlite3
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
        conn.commit()"""),

    # ── Useful Utilities ──
    ("python/decorator-timer.md", "python", ["util", "pattern"],
     "Timing Decorator", "Decorator to measure and print function execution time.", "pattern",
     """import time
import functools

def timer(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        print(f'{func.__name__} took {elapsed:.4f}s')
        return result
    return wrapper

@timer
def slow_function():
    time.sleep(1)
    return 'done'"""),

    ("python/retry-decorator.md", "python", ["util", "net", "pattern"],
     "Retry Decorator", "Decorator to retry a function with exponential backoff on failure.", "pattern",
     """import time
import functools

def retry(max_attempts=3, delay=1, backoff=2, exceptions=(Exception,)):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            wait = delay
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions:
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(wait)
                    wait *= backoff
            return None
        return wrapper
    return decorator

@retry(max_attempts=5, delay=0.5)
def fetch_data(url):
    import urllib.request
    with urllib.request.urlopen(url, timeout=5) as resp:
        return resp.read()"""),

    ("python/regex-patterns.md", "python", ["string", "pattern"],
     "Common Regex Patterns", "Frequently used regular expression patterns for text processing.", "pattern",
     """import re

# Email validation
email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
re.match(email_pattern, 'user@example.com')

# URL extraction
url_pattern = r'https?://[^\\s<>\"\\']+'
re.findall(url_pattern, 'Visit https://example.com today!')

# Phone number (US)
phone_pattern = r'\\(?\\d{3}\\)?[-.\\s]?\\d{3}[-.\\s]?\\d{4}'

# Extract all hex colors
hex_color = r'#[0-9a-fA-F]{6}\\b'

# Split on commas (respecting quotes)
csv_split = re.findall(r'(?:[^,\"]|\"[^\"]*\")+', 'a,\"b,c\",d')

# Replace multiple spaces with one
re.sub(r'\\s+', ' ', 'hello   world')"""),

    ("python/json-processing.md", "python", ["io", "string"],
     "JSON Processing", "Loading, saving, filtering, and transforming JSON data.", "pattern",
     """import json

def flatten_json(data, parent_key='', sep='.'):
    \"\"\"Flatten nested JSON to dot-notation keys.\"\"\"
    items = []
    if isinstance(data, dict):
        for k, v in data.items():
            new_key = f'{parent_key}{sep}{k}' if parent_key else k
            if isinstance(v, (dict, list)):
                items.extend(flatten_json(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
    elif isinstance(data, list):
        for i, v in enumerate(data):
            new_key = f'{parent_key}[{i}]'
            if isinstance(v, (dict, list)):
                items.extend(flatten_json(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
    return dict(items)

def filter_json(data, predicate):
    \"\"\"Recursively filter dicts/lists where predicate(key, value) is True.\"\"\"
    if isinstance(data, dict):
        return {k: filter_json(v, predicate) for k, v in data.items()
                if predicate(k, v) and filter_json(v, predicate)}
    if isinstance(data, list):
        return [filter_json(item, predicate) for item in data
                if filter_json(item, predicate)]
    return data

def pretty_print(data, sort_keys=True):
    return json.dumps(data, indent=2, sort_keys=sort_keys, ensure_ascii=False)"""),

    # ── Crypto ──
    ("python/hashing-crypto.md", "python", ["crypto", "util"],
     "Hashing & Basic Crypto", "SHA-256 hashing, random tokens, and basic Fernet encryption.", "pattern",
     """import hashlib
import secrets
import base64
from cryptography.fernet import Fernet

# SHA-256 hash
def hash_string(text):
    return hashlib.sha256(text.encode()).hexdigest()

# Random secure token (e.g. for API keys)
def generate_token(length=32):
    return secrets.token_hex(length)

# Random URL-safe string
def generate_id(length=16):
    return secrets.token_urlsafe(length)

# Fernet symmetric encryption (key must be saved)
def generate_key():
    return Fernet.generate_key()

def encrypt_message(key, message):
    f = Fernet(key)
    return f.encrypt(message.encode())

def decrypt_message(key, token):
    f = Fernet(key)
    return f.decrypt(token).decode()

# Constant-time comparison (prevents timing attacks)
def secure_compare(a, b):
    return secrets.compare_digest(a, b)"""),

    # ── Testing ──
    ("python/unittest-pattern.md", "python", ["test"],
     "Unit Testing with unittest", "Standard unittest patterns: setup, assertions, mocks, and parameterized.", "pattern",
     """import unittest
from unittest.mock import Mock, patch

class TestMyModule(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Run once before all tests
        pass

    def setUp(self):
        # Run before each test
        self.data = {'key': 'value'}

    def test_basic_assertions(self):
        self.assertEqual(2 + 2, 4)
        self.assertTrue(True)
        self.assertIn('key', self.data)
        self.assertIsNone(None)
        self.assertRaises(ValueError, int, 'not_a_number')

    @patch('module.external_api')
    def test_with_mock(self, mock_api):
        mock_api.return_value = {'status': 'ok'}
        result = my_function()
        mock_api.assert_called_once_with(expected_arg)

    def test_exception_handling(self):
        with self.assertRaises(ValueError) as ctx:
            parse_bad_input('')
        self.assertIn('invalid', str(ctx.exception))

if __name__ == '__main__':
    unittest.main()"""),

    ("python/pytest-pattern.md", "python", ["test"],
     "Testing with pytest", "Modern pytest patterns: fixtures, parametrize, tmp_path, capsys.", "pattern",
     """import pytest

# Fixtures
@pytest.fixture
def db():
    \"\"\"Set up and tear down a test database.\"\"\"
    db = create_database(':memory:')
    db.seed()
    yield db
    db.close()

# Parametrized tests
@pytest.mark.parametrize('input,expected', [
    (2, 4),
    (0, 0),
    (-3, 9),
])
def test_square(input, expected):
    assert input * input == expected

# Temp files
def test_file_processing(tmp_path):
    d = tmp_path / 'sub'
    d.mkdir()
    f = d / 'test.txt'
    f.write_text('hello')
    assert f.read_text() == 'hello'

# Capture stdout
def test_output(capsys):
    print('hello world')
    captured = capsys.readouterr()
    assert captured.out == 'hello world\\n'

# Test exceptions
def test_error():
    with pytest.raises(ValueError, match='invalid'):
        raise ValueError('invalid input')"""),

    # ═══════════════════════════════════════════════════════════
    #  JAVASCRIPT
    # ═══════════════════════════════════════════════════════════

    ("javascript/async-patterns.md", "javascript", ["async", "pattern", "net"],
     "Async/Await Patterns", "Modern async/await with error handling, parallel execution, and timeouts.", "pattern",
     """// Parallel execution with Promise.all
async function fetchAll(urls) {
    try {
        const results = await Promise.all(
            urls.map(url => fetch(url).then(r => r.json()))
        );
        return results;
    } catch (error) {
        console.error('One or more requests failed:', error);
        throw error;
    }
}

// Sequential with error handling
async function processSequential(items) {
    const results = [];
    for (const item of items) {
        try {
            const result = await processItem(item);
            results.push(result);
        } catch (err) {
            results.push({ error: err.message, item });
        }
    }
    return results;
}

// Timeout wrapper
function withTimeout(promise, ms = 5000) {
    const timeout = new Promise((_, reject) =>
        setTimeout(() => reject(new Error('Timeout')), ms)
    );
    return Promise.race([promise, timeout]);
}

// Retry with backoff
async function retry(fn, maxRetries = 3, delay = 1000) {
    for (let i = 0; i < maxRetries; i++) {
        try {
            return await fn();
        } catch (err) {
            if (i === maxRetries - 1) throw err;
            await new Promise(r => setTimeout(r, delay * Math.pow(2, i)));
        }
    }
}"""),

    ("javascript/fetch-api.md", "javascript", ["web", "net", "api"],
     "Fetch API", "HTTP requests with the Fetch API: GET, POST, headers, error handling, uploads.", "pattern",
     """// GET with error handling
async function getJSON(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
}

// POST with JSON body
async function postJSON(url, data) {
    const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    if (!response.ok) throw new Error(`POST failed: ${response.status}`);
    return response.json();
}

// Upload file
async function uploadFile(url, file) {
    const formData = new FormData();
    formData.append('file', file);
    const response = await fetch(url, { method: 'POST', body: formData });
    return response.json();
}

// Download file as blob
async function downloadFile(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error('Download failed');
    return response.blob();
}"""),

    # ═══════════════════════════════════════════════════════════
    #  GO
    # ═══════════════════════════════════════════════════════════

    ("go/http-server.md", "go", ["web", "api", "server"],
     "HTTP Server", "Basic HTTP server with routing, middleware, JSON responses, and graceful shutdown.", "pattern",
     """package main

import (
    "encoding/json"
    "log"
    "net/http"
    "os"
    "os/signal"
    "syscall"
)

func main() {
    mux := http.NewServeMux()
    mux.HandleFunc("/api/health", handleHealth)
    mux.HandleFunc("/api/items", handleItems)
    mux.HandleFunc("/api/items/", handleItemByID)

    server := &http.Server{Addr: ":8080", Handler: loggingMiddleware(mux)}

    // Graceful shutdown
    go func() {
        sig := make(chan os.Signal, 1)
        signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
        <-sig
        log.Println("Shutting down...")
        server.Close()
    }()

    log.Println("Listening on :8080")
    log.Fatal(server.ListenAndServe())
}

func loggingMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        log.Printf("%s %s", r.Method, r.URL.Path)
        next.ServeHTTP(w, r)
    })
}

func writeJSON(w http.ResponseWriter, status int, data interface{}) {
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(status)
    json.NewEncoder(w).Encode(data)
}

func handleHealth(w http.ResponseWriter, r *http.Request) {
    writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func handleItems(w http.ResponseWriter, r *http.Request) {
    if r.Method == "GET" {
        writeJSON(w, http.StatusOK, []interface{}{})
    } else {
        http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
    }
}

func handleItemByID(w http.ResponseWriter, r *http.Request) {
    writeJSON(w, http.StatusOK, map[string]interface{}{"id": 1})
}"""),

    ("go/file-ops.md", "go", ["io", "file"],
     "File Operations", "Read/write files, walk directories, JSON config loading in Go.", "pattern",
     """package main

import (
    "encoding/json"
    "fmt"
    "os"
    "path/filepath"
)

// ReadFile reads a file and returns its contents as a string.
func ReadFile(path string) (string, error) {
    data, err := os.ReadFile(path)
    if err != nil {
        return "", fmt.Errorf("reading %s: %w", path, err)
    }
    return string(data), nil
}

// WriteFile writes data to a file, creating directories if needed.
func WriteFile(path, data string) error {
    dir := filepath.Dir(path)
    if err := os.MkdirAll(dir, 0755); err != nil {
        return fmt.Errorf("creating dir %s: %w", dir, err)
    }
    return os.WriteFile(path, []byte(data), 0644)
}

// WalkFiles walks a directory, calling fn for each file.
func WalkFiles(root string, fn func(path string) error) error {
    return filepath.Walk(root, func(path string, info os.FileInfo, err error) error {
        if err != nil {
            return err
        }
        if info.IsDir() {
            return nil
        }
        return fn(path)
    })
}

// LoadJSON reads and unmarshals a JSON config file.
func LoadJSON(path string, target interface{}) error {
    data, err := os.ReadFile(path)
    if err != nil {
        return err
    }
    return json.Unmarshal(data, target)
}

// FileExists checks if a file exists and is not a directory.
func FileExists(path string) bool {
    info, err := os.Stat(path)
    return err == nil && !info.IsDir()
}"""),

    # ═══════════════════════════════════════════════════════════
    #  RUST
    # ═══════════════════════════════════════════════════════════

    ("rust/cli-app.md", "rust", ["cli", "io"],
     "CLI Application", "Rust CLI app with clap argument parsing and error handling.", "pattern",
     """use std::fs;
use std::path::PathBuf;
use clap::Parser;

#[derive(Parser)]
#[command(name = "mytool", version, about = "Does awesome things")]
struct Cli {
    /// Input file path
    input: PathBuf,

    /// Output file path
    #[arg(short, long, default_value = "output.txt")]
    output: PathBuf,

    /// Verbose mode
    #[arg(short, long)]
    verbose: bool,

    /// Max items to process
    #[arg(long, default_value_t = 10)]
    limit: usize,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cli = Cli::parse();

    if cli.verbose {
        eprintln!("Reading from: {:?}", cli.input);
        eprintln!("Writing to: {:?}", cli.output);
    }

    let content = fs::read_to_string(&cli.input)?;
    let processed = process_content(&content, cli.limit);
    fs::write(&cli.output, &processed)?;

    println!("Done. Wrote {} bytes to {:?}", processed.len(), cli.output);
    Ok(())
}

fn process_content(content: &str, _limit: usize) -> String {
    content.to_uppercase()
}"""),

    # ═══════════════════════════════════════════════════════════
    #  SHELL
    # ═══════════════════════════════════════════════════════════

    ("shell/file-processing.md", "shell", ["file", "util", "cli"],
     "File Processing Scripts", "Common shell one-liners and scripts for file processing.", "pattern",
     """#!/usr/bin/env bash
set -euo pipefail

# Loop over files with extension
for f in *.txt; do
    echo "Processing $f"
    wc -l "$f"
done

# Find and replace in files
find . -name '*.py' -type f -exec sed -i '' 's/old_text/new_text/g' {} +

# Backup files with date
for f in *.config; do
    cp "$f" "${f}.bak.$(date +%Y%m%d)"
done

# Batch rename (prefix)
for f in *.jpg; do
    mv "$f" "vacation_$f"
done

# Check disk usage per directory
du -sh */ | sort -rh | head -10

# Extract tar.gz
tar -xzf archive.tar.gz -C /target/dir

# Find large files (>100MB)
find . -type f -size +100M -exec ls -lh {} \\; | awk '{print $5, $NF}'

# Monitor log file in real-time
tail -f /var/log/system.log | grep --line-buffered ERROR

# CPU/memory per process
ps aux --sort=-%cpu | head -5"""),

    ("shell/git-workflow.md", "shell", ["git", "cli"],
     "Git Workflow Commands", "Common Git workflows: branching, merging, rebasing, squashing, cleanup.", "pattern",
     """#!/usr/bin/env bash
# ======= Workflow: Feature Branch =======
git checkout main
git pull origin main
git checkout -b feature/my-feature
# ... work, commit ...
git push -u origin feature/my-feature
# Open PR on GitHub

# ======= Workflow: Update branch from main =======
git fetch origin
git rebase origin/main          # cleaner history
# OR
git merge origin/main           # preserves merge commits

# ======= Workflow: Squash last N commits =======
git rebase -i HEAD~3            # pick first, squash rest

# ======= Workflow: Undo last commit (keep changes) =======
git reset --soft HEAD~1

# ======= Workflow: Undo last commit (discard changes) =======
git reset --hard HEAD~1

# ======= Workflow: Interactive add =======
git add -p                      # stage changes hunk by hunk

# ======= Workflow: Stash =======
git stash push -m 'WIP: feature X'
git stash list
git stash pop
git stash drop stash@{0}

# ======= Cleanup: Delete merged branches =======
git branch --merged main | grep -v '\\*\\|main' | xargs -r git branch -d

# ======= Show file from another branch =======
git show other-branch:path/to/file.py"""),

    ("shell/docker-workflow.md", "shell", ["docker", "cli"],
     "Docker Commands", "Common Docker workflows: build, run, compose, cleanup, debugging.", "pattern",
     """#!/usr/bin/env bash
# ======= Build & Run =======
docker build -t myapp:latest .
docker run -d --name myapp -p 8080:80 myapp:latest

# ======= Docker Compose =======
docker compose up -d                            # start all services
docker compose down                             # stop and remove
docker compose logs -f                          # follow all logs
docker compose logs web -f                      # follow one service
docker compose exec web bash                    # shell into running container
docker compose restart web                      # restart one service

# ======= Images & Containers =======
docker ps                                       # running containers
docker ps -a                                    # all containers
docker images                                   # all images
docker rmi <image_id>                           # remove image
docker rm <container_id>                        # remove container
docker system prune -f                          # clean up dangling resources
docker system prune -a --volumes                # clean up EVERYTHING

# ======= Debugging =======
docker logs <container_id>                      # see logs
docker exec -it <container_id> sh               # shell into container
docker inspect <container_id>                   # detailed info
docker stats                                    # live resource usage

# ======= Copy files =======
docker cp <container_id>:/app/output.txt ./
docker cp ./input.txt <container_id>:/app/"""),

    # ═══════════════════════════════════════════════════════════
    #  GENERIC / CROSS-LANGUAGE
    # ═══════════════════════════════════════════════════════════

    ("generic/common-algorithms.md", "generic", ["algorithm"],
     "Common Algorithms Reference", "Quick reference for common algorithm complexities and patterns.", "reference",
     """# Algorithm Complexity Reference

## Sorting
| Algorithm    | Best    | Average | Worst   | Space  | Stable |
|-------------|---------|---------|---------|--------|--------|
| Quick Sort  | O(n log n) | O(n log n) | O(n²) | O(log n) | No  |
| Merge Sort  | O(n log n) | O(n log n) | O(n log n) | O(n) | Yes |
| Heap Sort   | O(n log n) | O(n log n) | O(n log n) | O(1) | No  |
| Insertion   | O(n)    | O(n²)   | O(n²)   | O(1)   | Yes |
| Bubble      | O(n)    | O(n²)   | O(n²)   | O(1)   | Yes |

## Search
| Algorithm         | Time       | Space  | Requires |
|------------------|------------|--------|----------|
| Linear Search    | O(n)       | O(1)   | Nothing  |
| Binary Search    | O(log n)   | O(1)   | Sorted   |
| BFS (graph)      | O(V + E)   | O(V)   | Graph    |
| DFS (graph)      | O(V + E)   | O(V)   | Graph    |
| Dijkstra         | O(E log V) | O(V)   | + weights|
| A*               | O(E)       | O(V)   | Heuristic|

## Data Structures
| Structure    | Access | Search | Insert | Delete |
|-------------|--------|--------|--------|--------|
| Array       | O(1)   | O(n)   | O(n)   | O(n)   |
| Linked List | O(n)   | O(n)   | O(1)   | O(1)   |
| Hash Table  | O(1)   | O(1)   | O(1)   | O(1)   |
| BST (balanced) | O(log n) | O(log n) | O(log n) | O(log n) |
| Heap        | O(1)¹  | O(n)   | O(log n) | O(log n) |
¹ Only min/max"""),

    ("generic/regex-cheatsheet.md", "generic", ["string", "pattern"],
     "Regex Cheatsheet", "Cross-language regex pattern reference with examples.", "reference",
     """# Regex Cheatsheet

## Basic Tokens
| Pattern  | Matches                    |
|---------|----------------------------|
| `.`     | Any character except newline|
| `\\d`    | Digit [0-9]                |
| `\\w`    | Word char [a-zA-Z0-9_]     |
| `\\s`    | Whitespace [ \\t\\n\\r\\f]   |
| `\\b`    | Word boundary              |
| `^`     | Start of string / line     |
| `$`     | End of string / line       |

## Quantifiers
| Pattern  | Meaning          |
|---------|------------------|
| `*`     | 0 or more        |
| `+`     | 1 or more        |
| `?`     | 0 or 1 (optional)|
| `{n}`   | Exactly n times  |
| `{n,}`  | n or more        |
| `{n,m}` | Between n and m  |

## Groups & Lookarounds
| Pattern           | Meaning                |
|------------------|------------------------|
| `(abc)`          | Capturing group        |
| `(?:abc)`        | Non-capturing group    |
| `(?=abc)`        | Positive lookahead     |
| `(?!abc)`        | Negative lookahead     |
| `(?<=abc)`       | Positive lookbehind    |
| `(?<!abc)`       | Negative lookbehind    |

## Common Patterns
| Pattern                     | Matches                      |
|----------------------------|------------------------------|
| `^[\\w.-]+@[\\w.-]+\\\\.\\w{2,}$` | Email address            |
| `https?://[^\\s]+`           | URL                          |
| `\\d{3}-\\d{3}-\\d{4}`       | US phone (123-456-7890)      |
| `^#([0-9a-fA-F]{6})\\b`     | Hex color (#ff0000)          |
| `(?<!\\w)\\w{16}(?!\\w)`     | 16-char token (API keys)     |
| `<[^>]+>`                   | HTML tags                    |
| `"([^\"\\\\]*(?:\\\\.[^\"\\\\]*)*)"` | Double-quoted string  |
"""),

    ("generic/api-design.md", "generic", ["api", "web", "pattern"],
     "REST API Design Patterns", "RESTful API conventions: URLs, status codes, pagination, errors, versioning.", "reference",
     """# REST API Design Patterns

## URL Structure
```
GET    /api/resource          # List all
GET    /api/resource/:id      # Get one
POST   /api/resource          # Create
PUT    /api/resource/:id      # Replace
PATCH  /api/resource/:id      # Partial update
DELETE /api/resource/:id      # Delete
```

## HTTP Status Codes
- `200 OK` — Success
- `201 Created` — Resource created
- `204 No Content` — Deletion success
- `400 Bad Request` — Invalid input
- `401 Unauthorized` — No auth
- `403 Forbidden` — No permission
- `404 Not Found` — Resource missing
- `409 Conflict` — Duplicate/stale
- `422 Unprocessable` — Validation errors
- `429 Too Many Requests` — Rate limit
- `500 Internal Server Error` — Server fault

## Pagination
```
GET /api/items?page=2&per_page=50

Response:
{
  "data": [...],
  "meta": {
    "page": 2,
    "per_page": 50,
    "total": 1024,
    "total_pages": 21
  }
}
```

## Error Response
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Name is required",
    "details": [
      {"field": "name", "message": "must not be empty"}
    ]
  }
}
```

## Versioning
- URL: `/api/v1/resource`
- Header: `Accept: application/vnd.app.v2+json`
"""),
]
