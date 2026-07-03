---
language: markdown
tags: [documentation, readme, template]
title: README Template Guide
description: README structure — what/why/how, badges, installation, quickstart, API reference, contributing, and license. Includes a reusable markdown template.
source: pattern
---

# README Template Guide

A well-written README answers three questions:

- **What** is this project?
- **Why** should I use it?
- **How** do I get started, use it, and contribute?

Below is a reusable template covering every section.

---

```markdown
<!--
  Title — match the repository name.
  Badges — CI status, version, license, coverage, downloads.
-->
# Project Name

[![CI](https://github.com/user/project/actions/workflows/ci.yml/badge.svg)](https://github.com/user/project/actions)
[![npm version](https://img.shields.io/npm/v/project-name)](https://www.npmjs.com/package/project-name)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

> One-line tagline: "A fast, typed HTTP client with zero dependencies."

## Overview

Explain what the project does and why it exists. Keep it short — two or three paragraphs max. Include a code example right here so readers immediately see the API.

```python
from mylib import Client

client = Client(base_url="https://api.example.com")
data = client.fetch("/endpoint")
print(data)
```

## Installation

### Prerequisites
- Python 3.10+
- pip / uv / poetry

```bash
pip install project-name
```

Or using `uv`:

```bash
uv add project-name
```

## Quickstart

A minimal, runnable example from zero to working output.

```python
from project import Processor

proc = Processor()
result = proc.run("input.txt")
print(result)
```

## API Reference

Document public functions, classes, and methods. For larger projects, link to generated docs.

### `Processor.run(path: str) -> Result`

| Parameter | Type   | Description                 |
|-----------|--------|-----------------------------|
| `path`    | `str`  | Path to the input file      |

Returns a `Result` dataclass with `.status`, `.data`, and `.errors` fields.

### `Client(base_url, timeout=30)`

Creates an HTTP client pointing at `base_url`. Set `timeout` in seconds.

## Configuration

Explain environment variables, config files, or CLI flags:

| Env Variable      | Default     | Description                |
|-------------------|-------------|----------------------------|
| `MYAPP_DEBUG`     | `false`     | Enable verbose logging     |
| `MYAPP_PORT`      | `8080`      | HTTP server listen port    |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/my-feature`)
3. Commit your changes (`git commit -m 'feat: add my feature'`)
4. Push to the branch (`git push origin feat/my-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## Acknowledgements

- Inspired by [Awesome Project](https://github.com/user/awesome)
- Logo design by …
```
```

## Key Principles

- **Show, don't tell** — lead with a code example in the Overview
- **Keep it current** — update README when the API changes
- **Badges for at-a-glance status** — CI, version, coverage, license
- **One `#` for the title**, `##` for sections, `###` for subsections
- **Link to deeper docs** — don't inline everything
