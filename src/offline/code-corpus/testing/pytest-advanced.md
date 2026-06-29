---
language: python
tags: [pytest, testing, python, fixtures]
title: Advanced Pytest Testing
description: Comprehensive guide to advanced pytest features including fixtures (scope), conftest.py, parametrize, markers, mocking with monkeypatch/unittest.mock, coverage, and xdist parallel testing
source: pattern
---

# Advanced Pytest Testing

## Fixtures and Scopes

```python
import pytest
import tempfile
import os
from pathlib import Path


# ─── Fixture Scopes ───────────────────────────────────────────────────────────

@pytest.fixture(scope='function')  # Default: run once per test function
def temp_file():
    """Create a temporary file that's cleaned up after each test."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write('initial content')
        temp_path = f.name
    yield temp_path
    os.unlink(temp_path)


@pytest.fixture(scope='class')  # Run once per test class
def class_scope_data():
    """Shared data for all tests in a class."""
    return {'shared': 'data', 'counter': 0}


@pytest.fixture(scope='module')  # Run once per test module
def db_connection():
    """Set up a database connection once for all tests in this module."""
    print("\nSetting up database connection...")
    conn = {"connected": True, "db": "test_db"}
    yield conn
    print("\nClosing database connection...")
    conn["connected"] = False


@pytest.fixture(scope='session')  # Run once per test session
def global_config():
    """Load configuration once for all tests."""
    return {
        'base_url': 'http://testserver.com',
        'api_key': 'test-key',
        'timeout': 30
    }


# ─── Using Fixtures ───────────────────────────────────────────────────────────

def test_temp_file(temp_file):
    """Test using the function-scoped temp file fixture."""
    assert os.path.exists(temp_file)
    with open(temp_file) as f:
        assert f.read() == 'initial content'


class TestClassScope:
    def test_first(self, class_scope_data):
        class_scope_data['counter'] += 1
        assert class_scope_data['counter'] == 1
    
    def test_second(self, class_scope_data):
        # Counter persists from test_first because scope='class'
        assert class_scope_data['counter'] == 1  # Reset for class scope
        class_scope_data['counter'] += 1
        assert class_scope_data['counter'] == 1  # Wait — class scope resets? 
        # Actually class scope persists, so counter would be 1 still


def test_db_connection(db_connection):
    assert db_connection['connected'] is True


def test_global_config(global_config):
    assert global_config['base_url'] == 'http://testserver.com'


# ─── Factory Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def make_user():
    """Factory fixture that creates users with custom attributes."""
    created_users = []
    
    def _create_user(name: str, email: str = None, admin: bool = False):
        user = {
            'name': name,
            'email': email or f'{name.lower()}@example.com',
            'admin': admin,
            'id': len(created_users) + 1
        }
        created_users.append(user)
        return user
    
    yield _create_user
    
    # Cleanup all created users
    for user in created_users:
        print(f"Cleaning up user: {user['name']}")


def test_factory_fixture(make_user):
    regular = make_user('Alice', admin=False)
    admin = make_user('Bob', admin=True)
    
    assert regular['admin'] is False
    assert admin['admin'] is True
    assert regular['id'] == 1
    assert admin['id'] == 2
```

## conftest.py

```python
# conftest.py (in the root of your tests directory)
"""
Global test configuration. Pytest automatically discovers conftest.py files
in test directories. Fixtures, hooks, and plugins defined here are available
to all tests in that directory and subdirectories.
"""
import pytest
from typing import Dict, Any
import json
import os


# ─── Global Fixtures Available to All Tests ───────────────────────────────────

@pytest.fixture(autouse=True)
def auto_setup_and_teardown():
    """Fixture that runs automatically before and after every test."""
    print("\n[SETUP] Test starting...")
    yield
    print("[TEARDOWN] Test complete.")


@pytest.fixture
def test_data_dir() -> str:
    """Path to test data fixtures directory."""
    return os.path.join(os.path.dirname(__file__), 'fixtures', 'data')


@pytest.fixture
def load_json_fixture(test_data_dir):
    """Factory fixture that loads JSON test data by filename."""
    def _loader(filename: str) -> Dict[str, Any]:
        filepath = os.path.join(test_data_dir, filename)
        with open(filepath) as f:
            return json.load(f)
    return _loader


# ─── Custom Hooks ─────────────────────────────────────────────────────────────

def pytest_collection_modifyitems(config, items):
    """Hook: modify test collection (e.g., skip tests on certain conditions)."""
    for item in items:
        # Add 'slow' marker to tests with 'slow' in their name
        if 'slow' in item.name:
            item.add_marker(pytest.mark.slow)


def pytest_addoption(parser):
    """Add custom command-line options."""
    parser.addoption(
        '--run-integration',
        action='store_true',
        default=False,
        help='Run integration tests (skipped by default)'
    )


def pytest_configure(config):
    """Register custom markers to suppress warnings."""
    config.addinivalue_line('markers', 'slow: marks tests as slow')
    config.addinivalue_line('markers', 'integration: marks tests as integration tests')
    config.addinivalue_line('markers', 'smoke: marks tests as smoke tests')
    config.addinivalue_line('markers', 'critical: marks tests as critical path')


# ─── Conditional Skipping Based on CLI Options ────────────────────────────────

def pytest_runtest_setup(item):
    """Skip integration tests unless --run-integration is passed."""
    if 'integration' in item.keywords and not item.config.getoption('--run-integration'):
        pytest.skip('Integration tests skipped. Use --run-integration to run.')
```

## Parametrize

```python
import pytest
import math


# ─── Basic Parametrization ────────────────────────────────────────────────────

@pytest.mark.parametrize('input_val, expected', [
    (1, 1),
    (2, 4),
    (3, 9),
    (4, 16),
    (5, 25),
])
def test_square(input_val, expected):
    assert input_val ** 2 == expected


# ─── Parametrize Multiple Arguments ───────────────────────────────────────────

@pytest.mark.parametrize('a, b, expected', [
    (1, 2, 3),
    (5, 5, 10),
    (0, 0, 0),
    (-1, 1, 0),
    (100, -50, 50),
])
def test_add(a, b, expected):
    assert a + b == expected


# ─── Parametrize with IDs ─────────────────────────────────────────────────────

@pytest.mark.parametrize('text, expected_length', [
    ('hello', 5),
    ('world!', 6),
    ('', 0),
    ('a b c', 5),
], ids=['simple', 'punctuation', 'empty', 'with_spaces'])
def test_string_length(text, expected_length):
    assert len(text) == expected_length


# ─── Combinatorial Parametrization ────────────────────────────────────────────

@pytest.mark.parametrize('operation', ['add', 'subtract', 'multiply', 'divide'])
@pytest.mark.parametrize('a', [1, 2, 3])
@pytest.mark.parametrize('b', [10, 20])
def test_operations(a, b, operation):
    """Tests 4 × 3 × 2 = 24 combinations."""
    if operation == 'add':
        assert a + b == b + a
    elif operation == 'subtract':
        assert a - b == -(b - a)
    elif operation == 'multiply':
        assert a * b == b * a
    elif operation == 'divide' and b != 0:
        assert (a / b) * b == a


# ─── Parametrize with Fixtures ────────────────────────────────────────────────

@pytest.fixture
def base_numbers():
    return [1, 2, 3, 4, 5]


@pytest.mark.parametrize('multiplier', [2, 3, 10])
def test_multiply_fixture(base_numbers, multiplier):
    results = [n * multiplier for n in base_numbers]
    expected = [n * multiplier for n in [1, 2, 3, 4, 5]]
    assert results == expected


# ─── Parametrize from External Data ───────────────────────────────────────────

def load_test_cases():
    """Could load from CSV, JSON, database, etc."""
    return [
        {'username': 'alice', 'expected_status': 200},
        {'username': 'bob', 'expected_status': 200},
        {'username': 'nonexistent', 'expected_status': 404},
    ]


@pytest.mark.parametrize('case', load_test_cases(), ids=lambda c: c['username'])
def test_from_external_data(case):
    assert case['expected_status'] in [200, 404]
```

## Markers

```python
import pytest


# ─── Built-in Markers ─────────────────────────────────────────────────────────

@pytest.mark.skip(reason="Feature not implemented yet")
def test_future_feature():
    assert False


@pytest.mark.skipif(
    __import__('sys').version_info < (3, 10),
    reason="Requires Python 3.10+"
)
def test_python_version_dependent():
    assert True


@pytest.mark.xfail(reason="Known bug #123", strict=False)
def test_known_bug():
    assert 1 + 1 == 3  # We know this fails


@pytest.mark.xfail(strict=True)
def test_expected_failure():
    """With strict=True, passing test would FAIL the suite."""
    raise AssertionError("This must fail")


# ─── Custom Markers ───────────────────────────────────────────────────────────

@pytest.mark.slow
def test_heavy_computation():
    import time
    time.sleep(2)
    assert sum(range(1000000)) == 499999500000


@pytest.mark.smoke
def test_critical_login():
    """Smoke test: verify login works."""
    assert True


@pytest.mark.integration
def test_database_integration():
    """Integration test: requires database."""
    assert True


@pytest.mark.critical
@pytest.mark.smoke
def test_critical_path():
    """Test can have multiple markers."""
    assert True


# ─── Custom Marker with Arguments ─────────────────────────────────────────────

@pytest.mark.timeout(5)
def test_with_timeout():
    import time
    time.sleep(1)
    assert True


# ─── Using -m to Select Tests ─────────────────────────────────────────────────
#
# Run only smoke tests:        pytest -m smoke
# Run all except slow:          pytest -m 'not slow'
# Run smoke OR critical:        pytest -m 'smoke or critical'
# Run smoke AND integration:    pytest -m 'smoke and integration'
# Run critical but not slow:    pytest -m 'critical and not slow'
```

## Mocking with monkeypatch and unittest.mock

```python
import pytest
from unittest.mock import Mock, patch, MagicMock, PropertyMock
import requests
import os
from datetime import datetime


# ─── monkeypatch ──────────────────────────────────────────────────────────────

def get_api_data(url: str) -> dict:
    """Simulates fetching data from an API."""
    response = requests.get(url)
    return response.json()


def read_config() -> dict:
    """Reads configuration from environment variables."""
    return {
        'host': os.environ.get('APP_HOST', 'localhost'),
        'port': int(os.environ.get('APP_PORT', '8080')),
        'debug': os.environ.get('APP_DEBUG', 'false').lower() == 'true'
    }


def test_monkeypatch_environment(monkeypatch):
    """Mock environment variables with monkeypatch."""
    monkeypatch.setenv('APP_HOST', 'test-server')
    monkeypatch.setenv('APP_PORT', '9000')
    monkeypatch.setenv('APP_DEBUG', 'true')
    
    config = read_config()
    assert config['host'] == 'test-server'
    assert config['port'] == 9000
    assert config['debug'] is True


def test_monkeypatch_function(monkeypatch):
    """Replace a function entirely."""
    
    def mock_get_api_data(url):
        return {'mocked': True, 'url': url}
    
    monkeypatch.setattr('__main__.get_api_data', mock_get_api_data)
    
    result = get_api_data('http://example.com')
    assert result['mocked'] is True


def test_monkeypatch_dict(monkeypatch):
    """Mock dictionary values."""
    monkeypatch.setitem(__import__('os').environ, 'DATABASE_URL', 'sqlite:///test.db')
    assert os.environ['DATABASE_URL'] == 'sqlite:///test.db'


def test_monkeypatch_class(monkeypatch):
    """Mock a class method."""
    class Calculator:
        def add(self, a, b):
            return a + b
    
    def mock_add(self, a, b):
        return a * b  # Returns product instead of sum
    
    monkeypatch.setattr(Calculator, 'add', mock_add)
    
    calc = Calculator()
    assert calc.add(2, 3) == 6  # Multiplication instead of addition


# ─── unittest.mock (patch decorator) ──────────────────────────────────────────

@patch('requests.get')
def test_api_call_with_patch_decorator(mock_get):
    """Mock requests.get using the patch decorator."""
    mock_response = Mock()
    mock_response.json.return_value = {'data': 'test', 'status': 'ok'}
    mock_response.status_code = 200
    mock_get.return_value = mock_response
    
    result = get_api_data('http://api.example.com/users')
    
    mock_get.assert_called_once_with('http://api.example.com/users')
    assert result == {'data': 'test', 'status': 'ok'}


@patch('requests.get')
@patch('os.environ.get')
def test_multiple_mocks(mock_env_get, mock_get):
    """Patch multiple dependencies."""
    mock_env_get.return_value = 'mock-value'
    mock_response = Mock()
    mock_response.json.return_value = {'success': True}
    mock_get.return_value = mock_response
    
    result = get_api_data('http://test.com')
    
    assert result['success'] is True
    mock_env_get.assert_called_with('SOME_VAR', 'default_value')
    mock_get.assert_called_once()


# ─── Context Manager Patching ─────────────────────────────────────────────────

def test_api_call_with_context_manager():
    """Use patch as a context manager."""
    with patch('requests.get') as mock_get:
        mock_response = Mock()
        mock_response.json.return_value = {'id': 1, 'name': 'Test'}
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        result = get_api_data('http://api.example.com/users/1')
        
        assert result['name'] == 'Test'
        assert result['id'] == 1


# ─── Mocking Properties ───────────────────────────────────────────────────────

class Database:
    @property
    def connection_string(self):
        return f"postgresql://user:pass@localhost:5432/db"
    
    @property
    def is_connected(self):
        return False
    
    def query(self, sql):
        return []


def test_mock_property():
    """Mock a class property using PropertyMock."""
    mock_db = Mock(spec=Database)
    
    # Mock property returns
    type(mock_db).connection_string = PropertyMock(
        return_value='sqlite:///test.db'
    )
    type(mock_db).is_connected = PropertyMock(return_value=True)
    mock_db.query.return_value = [{'id': 1, 'name': 'Alice'}]
    
    assert mock_db.connection_string == 'sqlite:///test.db'
    assert mock_db.is_connected is True
    assert mock_db.query('SELECT * FROM users') == [{'id': 1, 'name': 'Alice'}]


# ─── Mocking Side Effects ─────────────────────────────────────────────────────

def test_mock_side_effect():
    """Use side_effect for different return values on each call."""
    mock_fetch = Mock()
    
    # Different return values on consecutive calls
    mock_fetch.side_effect = [
        {'page': 1, 'data': ['a', 'b']},
        {'page': 2, 'data': ['c', 'd']},
        {'page': 3, 'data': []},
        StopIteration("No more pages"),
    ]
    
    page1 = mock_fetch()
    assert page1['page'] == 1
    
    page2 = mock_fetch()
    assert page2['page'] == 2
    
    page3 = mock_fetch()
    assert page3['data'] == []
    
    import pytest
    with pytest.raises(StopIteration):
        mock_fetch()


def test_mock_side_effect_exception():
    """Use side_effect to raise exceptions."""
    mock_api = Mock()
    mock_api.get_user.side_effect = ValueError("User not found")
    
    with pytest.raises(ValueError, match="User not found"):
        mock_api.get_user(999)


# ─── Mocking Async Functions ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_async_mock():
    """Mock async functions."""
    mock_fetch = AsyncMock()
    mock_fetch.return_value = {'status': 'ok'}
    
    result = await mock_fetch('/api/health')
    assert result['status'] == 'ok'
    mock_fetch.assert_awaited_once_with('/api/health')
```

## Coverage Configuration

```ini
# .coveragerc
[run]
source = src
omit = 
    */tests/*
    */migrations/*
    *__init__.py
    */__main__.py

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise NotImplementedError
    if __name__ == .__main__.:
    pass
    raise AssertionError
show_missing = True
skip_covered = True
ignore_errors = True

[html]
directory = coverage_html
```

```python
# Running with coverage
# pytest --cov=src/ --cov-report=term-missing --cov-report=html
# pytest --cov=src/ --cov-report=xml:coverage.xml
# pytest --cov=src/ --cov-fail-under=80  # Fail if coverage < 80%
```

## xdist Parallel Testing

```python
"""
# Running tests in parallel with pytest-xdist:

# Run on all available CPUs:
pytest -n auto

# Run on 4 workers:
pytest -n 4

# Distribute tests by mode:
pytest -n 4 --dist load        # Default: load balance
pytest -n 4 --dist loadscope   # Group by module/class
pytest -n 4 --dist loadfile    # Group by test file
pytest -n 4 --dist worksteal   # Newer: steal work from idle workers

# Combine with other flags:
pytest -n auto -v --tb=short --cov=src/
pytest -n 4 -x --timeout=60

# Important: xdist isolation
# Each worker gets its own process, so module-scoped fixtures run per worker.
# Use --dist loadscope to keep module-scoped fixtures together on one worker.
"""
```

## Complete Test Example

```python
import pytest
from unittest.mock import Mock, patch
import json
from datetime import datetime


# ─── Example Module to Test ──────────────────────────────────────────────────

class UserService:
    def __init__(self, db, api_client):
        self.db = db
        self.api = api_client
    
    def get_user(self, user_id: int) -> dict:
        """Fetch a user from the database with enrichment from API."""
        user = self.db.query("SELECT * FROM users WHERE id = ?", [user_id])
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        # Enrich with external data
        external_data = self.api.fetch_user_data(user_id)
        user['external_data'] = external_data
        user['last_synced'] = datetime.utcnow().isoformat()
        
        return user
    
    def create_user(self, name: str, email: str) -> int:
        """Create a new user and sync with external service."""
        if not name or not email:
            raise ValueError("Name and email are required")
        
        user_id = self.db.insert(
            "INSERT INTO users (name, email) VALUES (?, ?)",
            [name, email]
        )
        
        self.api.sync_user({'id': user_id, 'name': name, 'email': email})
        
        return user_id


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestUserService:
    @pytest.fixture
    def mock_db(self):
        return Mock()
    
    @pytest.fixture
    def mock_api(self):
        return Mock()
    
    @pytest.fixture
    def service(self, mock_db, mock_api):
        return UserService(mock_db, mock_api)
    
    def test_get_user_success(self, service, mock_db, mock_api):
        # Arrange
        mock_db.query.return_value = {
            'id': 1, 'name': 'Alice', 'email': 'alice@example.com'
        }
        mock_api.fetch_user_data.return_value = {'premium': True, 'tier': 'gold'}
        
        # Act
        result = service.get_user(1)
        
        # Assert
        assert result['name'] == 'Alice'
        assert result['external_data']['tier'] == 'gold'
        assert 'last_synced' in result
        
        mock_db.query.assert_called_once()
        mock_api.fetch_user_data.assert_called_once_with(1)
    
    def test_get_user_not_found(self, service, mock_db, mock_api):
        # Arrange
        mock_db.query.return_value = None
        
        # Act & Assert
        with pytest.raises(ValueError, match="User 999 not found"):
            service.get_user(999)
        
        mock_api.fetch_user_data.assert_not_called()
    
    @pytest.mark.parametrize('name, email, expected_error', [
        ('', 'alice@test.com', 'Name and email are required'),
        ('Alice', '', 'Name and email are required'),
        ('', '', 'Name and email are required'),
    ])
    def test_create_user_validation(self, service, name, email, expected_error):
        with pytest.raises(ValueError, match=expected_error):
            service.create_user(name, email)
    
    def test_create_user_success(self, service, mock_db, mock_api):
        # Arrange
        mock_db.insert.return_value = 42
        
        # Act
        user_id = service.create_user('Bob', 'bob@test.com')
        
        # Assert
        assert user_id == 42
        mock_db.insert.assert_called_once()
        mock_api.sync_user.assert_called_once_with({
            'id': 42, 'name': 'Bob', 'email': 'bob@test.com'
        })
    
    @pytest.mark.slow
    def test_performance(self, service, mock_db, mock_api):
        """Performance test (marked as slow)."""
        import time
        mock_db.query.return_value = {'id': 1, 'name': 'Test'}
        mock_api.fetch_user_data.return_value = {}
        
        start = time.time()
        for i in range(100):
            service.get_user(1)
        duration = time.time() - start
        
        assert duration < 1.0  # 100 calls should take less than 1 second
```