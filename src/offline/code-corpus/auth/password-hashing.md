---
language: python
tags: [auth, security, passwords, bcrypt, hashing]
title: Password Hashing
description: bcrypt (hash + verify), argon2 (modern alternative), salt, pepper, password policy validation
source: pattern
---

# Password Hashing

## bcrypt — Hash & Verify

```python
import bcrypt


def hash_password_bcrypt(password: str) -> str:
    """
    Hash a password using bcrypt.
    bcrypt automatically generates and embeds a random salt.
    The returned string includes: algorithm, cost, salt, and hash.
    """
    # Convert password to bytes
    password_bytes = password.encode("utf-8")

    # Generate salt (12 rounds is a good balance of security and speed)
    salt = bcrypt.gensalt(rounds=12)

    # Hash the password
    hashed = bcrypt.hashpw(password_bytes, salt)

    # Return as a string (e.g., b'$2b$12$...')
    return hashed.decode("utf-8")


def verify_password_bcrypt(password: str, hashed: str) -> bool:
    """
    Verify a password against a bcrypt hash.
    bcrypt extracts the salt from the stored hash automatically.
    """
    password_bytes = password.encode("utf-8")
    hashed_bytes = hashed.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_bytes)


# Example usage
if __name__ == "__main__":
    plain_password = "SecureP@ssw0rd!"
    hashed = hash_password_bcrypt(plain_password)
    print(f"Hash: {hashed}")

    assert verify_password_bcrypt(plain_password, hashed) is True
    assert verify_password_bcrypt("WrongPassword", hashed) is False
    print("bcrypt hash/verify: OK")
```

## Argon2 — Modern Alternative

```python
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

# Argon2 is the winner of the Password Hashing Competition (PHC)
# It's memory-hard and resistant to GPU/ASIC attacks

ph = PasswordHasher(
    time_cost=3,          # Number of iterations
    memory_cost=65536,    # 64 MB memory usage
    parallelism=4,        # Number of parallel threads
    hash_len=32,          # Length of the hash in bytes
    salt_len=16,          # Length of the random salt
)


def hash_password_argon2(password: str) -> str:
    """
    Hash a password using Argon2id (recommended variant).
    Returns a string containing all parameters and the hash.
    """
    return ph.hash(password)


def verify_password_argon2(password: str, hashed: str) -> bool:
    """
    Verify a password against an Argon2 hash.
    """
    try:
        return ph.verify(hashed, password)
    except VerifyMismatchError:
        return False
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    """
    Check if a hash needs to be re-computed with updated parameters.
    Useful when you increase time_cost or memory_cost over time.
    """
    return ph.check_needs_rehash(hashed)


# Example usage
if __name__ == "__main__":
    password = "MySecureP@ss!"

    hashed = hash_password_argon2(password)
    print(f"Argon2 hash: {hashed}")

    assert verify_password_argon2(password, hashed) is True
    assert verify_password_argon2("WrongPassword", hashed) is False
    print("Argon2 hash/verify: OK")

    # Upgrade hash parameters if needed
    if needs_rehash(hashed):
        new_hash = hash_password_argon2(password)
        print("Hash upgraded with new parameters")
```

## Salt & Pepper Pattern

```python
import os
import hashlib
import hmac

# Pepper: a server-side secret added BEFORE hashing
# Unlike salt (stored with hash), pepper is stored separately (env var, HSM, KMS)
PEPPER = os.environ.get("PASSWORD_PEPPER", "server-side-secret-pepper")


def generate_salt(length: int = 32) -> str:
    """Generate a cryptographically random salt."""
    return os.urandom(length).hex()


def hash_password_with_salt_and_pepper(password: str, salt: str) -> str:
    """
    Hash password with both salt and pepper.

    Salt: unique per user, stored in DB alongside hash.
    Pepper: same for all users, stored server-side only.

    Process: pepper is mixed in using HMAC, then bcrypt hashes the result.
    """
    # Step 1: Apply pepper via HMAC-SHA256
    peppered = hmac.new(
        PEPPER.encode("utf-8"),
        password.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    # Step 2: Prepend salt
    salted = salt + peppered

    # Step 3: Hash with bcrypt
    return bcrypt.hashpw(salted.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password_with_salt_and_pepper(password: str, salt: str, hashed: str) -> bool:
    """Verify a password that was hashed with salt + pepper."""
    peppered = hmac.new(
        PEPPER.encode("utf-8"),
        password.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    salted = salt + peppered
    return bcrypt.checkpw(salted.encode("utf-8"), hashed.encode("utf-8"))


# User storage example
class UserPasswordStore:
    """Example of how to store hashed passwords with salt."""
    def __init__(self, user_id: str, password: str):
        self.user_id = user_id
        self.salt = generate_salt()
        self.hash = hash_password_with_salt_and_pepper(password, self.salt)

    def verify(self, password: str) -> bool:
        return verify_password_with_salt_and_pepper(password, self.salt, self.hash)
```

## Password Policy Validation

```python
import re
from typing import List, Tuple


class PasswordPolicy:
    """
    Enforce password strength requirements.
    Returns a list of (passed: bool, message: str) results.
    """

    def __init__(
        self,
        min_length: int = 12,
        max_length: int = 128,
        require_uppercase: bool = True,
        require_lowercase: bool = True,
        require_digit: bool = True,
        require_special: bool = True,
        exclude_common: bool = True,
        max_repeated: int = 3,
    ):
        self.min_length = min_length
        self.max_length = max_length
        self.require_uppercase = require_uppercase
        self.require_lowercase = require_lowercase
        self.require_digit = require_digit
        self.require_special = require_special
        self.exclude_common = exclude_common
        self.max_repeated = max_repeated

        # Common passwords to reject
        self.common_passwords = {
            "password", "password123", "123456", "12345678",
            "qwerty", "admin", "letmein", "welcome",
            "monkey", "dragon", "master", "abc123",
            "passw0rd", "p@ssword", "P@ssw0rd",
        }

    def validate(self, password: str) -> Tuple[bool, List[str]]:
        """Validate a password against all policy rules."""
        errors: List[str] = []

        # Length checks
        if len(password) < self.min_length:
            errors.append(f"Password must be at least {self.min_length} characters")

        if len(password) > self.max_length:
            errors.append(f"Password must be at most {self.max_length} characters")

        # Character type checks
        if self.require_uppercase and not re.search(r"[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")

        if self.require_lowercase and not re.search(r"[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")

        if self.require_digit and not re.search(r"\d", password):
            errors.append("Password must contain at least one digit")

        if self.require_special and not re.search(r"[!@#$%^&*(),.?\":{}|<>_\-+=~`\[\];']", password):
            errors.append("Password must contain at least one special character")

        # Common password check
        if self.exclude_common and password.lower() in self.common_passwords:
            errors.append("This password is too common. Choose a more unique password")

        # Repeated characters check
        if self.max_repeated:
            pattern = r"(.)\1{" + str(self.max_repeated - 1) + r",}"
            if re.search(pattern, password):
                errors.append(f"Password must not contain more than {self.max_repeated} repeated characters in a row")

        # Check for sequential patterns
        sequences = ["abcdefghijklmnopqrstuvwxyz", "0123456789", "qwertyuiop", "asdfghjkl", "zxcvbnm"]
        lower_pass = password.lower()
        for seq in sequences:
            for i in range(len(seq) - 3):
                if seq[i:i+4] in lower_pass:
                    errors.append("Password contains a sequential pattern")
                    break
            if errors and "sequential" in errors[-1]:
                break

        return (len(errors) == 0, errors)


# Usage example
def create_user_with_password(email: str, password: str) -> dict:
    """Register a user with proper password hashing and policy validation."""
    policy = PasswordPolicy()
    valid, errors = policy.validate(password)

    if not valid:
        return {"success": False, "errors": errors}

    hashed = hash_password_argon2(password)
    # Store in database: db.create_user(email=email, password_hash=hashed, salt=...)

    return {
        "success": True,
        "message": "User created",
        "password_hash_preview": hashed[:30] + "...",
    }


if __name__ == "__main__":
    # Test password validation
    policy = PasswordPolicy()
    test_passwords = [
        "short",
        "onlylowercase",
        "MissingDigit!",
        "ValidP@ss123",
        "password",  # Common password
        "aaaa1234!!!",  # Repeated chars
        "C0mplex!V@lid#2024",
    ]

    for pw in test_passwords:
        valid, errors = policy.validate(pw)
        status = "✓ VALID" if valid else f"✗ INVALID ({'; '.join(errors)})"
        print(f"  {pw:30s} → {status}")
```