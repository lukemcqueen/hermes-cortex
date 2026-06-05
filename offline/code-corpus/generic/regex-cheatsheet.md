---
language: generic
tags: [string, pattern]
title: Regex Cheatsheet
description: Cross-language regex pattern reference with examples.
source: reference
---

```generic
# Regex Cheatsheet

## Basic Tokens
| Pattern  | Matches                    |
|---------|----------------------------|
| `.`     | Any character except newline|
| `\d`    | Digit [0-9]                |
| `\w`    | Word char [a-zA-Z0-9_]     |
| `\s`    | Whitespace [ \t\n\r\f]   |
| `\b`    | Word boundary              |
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
| `^[\w.-]+@[\w.-]+\\.\w{2,}$` | Email address            |
| `https?://[^\s]+`           | URL                          |
| `\d{3}-\d{3}-\d{4}`       | US phone (123-456-7890)      |
| `^#([0-9a-fA-F]{6})\b`     | Hex color (#ff0000)          |
| `(?<!\w)\w{16}(?!\w)`     | 16-char token (API keys)     |
| `<[^>]+>`                   | HTML tags                    |
| `"([^"\\]*(?:\\.[^"\\]*)*)"` | Double-quoted string  |

```
