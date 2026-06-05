---
language: python
tags: [crypto, util]
title: Hashing & Basic Crypto
description: SHA-256 hashing, random tokens, and basic Fernet encryption.
source: pattern
---

```python
import hashlib
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
    return secrets.compare_digest(a, b)
```
