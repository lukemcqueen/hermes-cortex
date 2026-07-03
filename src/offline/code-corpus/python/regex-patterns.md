---
language: python
tags: [string, pattern]
title: Common Regex Patterns
description: Frequently used regular expression patterns for text processing.
source: pattern
---

```python
import re

# Email validation
email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
re.match(email_pattern, 'user@example.com')

# URL extraction
url_pattern = r'https?://[^\s<>"\']+'
re.findall(url_pattern, 'Visit https://example.com today!')

# Phone number (US)
phone_pattern = r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'

# Extract all hex colors
hex_color = r'#[0-9a-fA-F]{6}\b'

# Split on commas (respecting quotes)
csv_split = re.findall(r'(?:[^,"]|"[^"]*")+', 'a,"b,c",d')

# Replace multiple spaces with one
re.sub(r'\s+', ' ', 'hello   world')

```
