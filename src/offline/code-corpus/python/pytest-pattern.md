---
language: python
tags: [test]
title: Testing with pytest
description: Modern pytest patterns: fixtures, parametrize, tmp_path, capsys.
source: pattern
---

```python
import pytest

# Fixtures
@pytest.fixture
def db():
    """Set up and tear down a test database."""
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
    assert captured.out == 'hello world\n'

# Test exceptions
def test_error():
    with pytest.raises(ValueError, match='invalid'):
        raise ValueError('invalid input')

```
