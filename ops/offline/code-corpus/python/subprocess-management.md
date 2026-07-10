---
language: python
tags: [sys, cli, util, pattern]
title: Subprocess Management
description: Running external commands with subprocess.run, capturing stdout/stderr, piping, timeout, error handling, and shell=False best practices.
source: pattern
---

```python
import os
import subprocess
import sys
from typing import Optional


def run(
    cmd: list[str],
    *,
    timeout: Optional[float] = None,
    check: bool = True,
    input_text: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """Run an external command, capture output, and raise on failure by default."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check,
            input=input_text,
        )
        return result
    except subprocess.CalledProcessError as exc:
        print(f"Command {cmd} failed with exit code {exc.returncode}", file=sys.stderr)
        print(f"stdout: {exc.stdout}", file=sys.stderr)
        print(f"stderr: {exc.stderr}", file=sys.stderr)
        raise
    except FileNotFoundError:
        print(f"Command not found: {cmd[0]}", file=sys.stderr)
        raise


def run_pipe(
    commands: list[list[str]],
    *,
    timeout: Optional[float] = None,
    check: bool = True,
) -> bytes:
    """Chain multiple commands via pipeline (left to right)."""
    prev_stdout: Optional[bytes] = None
    for i, cmd in enumerate(commands):
        stdin = subprocess.PIPE if i == 0 else prev_stdout
        proc = subprocess.Popen(
            cmd,
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = proc.communicate(timeout=timeout)
        if check and proc.returncode != 0:
            raise subprocess.CalledProcessError(
                proc.returncode, cmd, stdout, stderr
            )
        prev_stdout = stdout
    return prev_stdout or b""


def stream_output(cmd: list[str]) -> None:
    """Run a command and stream its output line-by-line in real time."""
    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    ) as proc:
        for line in proc.stdout:  # type: ignore[union-attr]
            print(line, end="")
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)


# ---- Example ---- #
if __name__ == "__main__":
    # Simple capture
    r = run(["echo", "hello subprocess"])
    print("Captured:", r.stdout.strip())

    # With stdin
    r2 = run(["tr", "[:lower:]", "[:upper:]"], input_text="hello world")
    print("Uppercased:", r2.stdout.strip())

    # Pipeline: ps aux | grep python | head -3
    try:
        out = run_pipe(
            [["ps", "aux"], ["grep", "python"], ["head", "-3"]],
            check=False,
        )
        print("Pipeline output:")
        print(out.decode("utf-8", errors="replace"))
    except FileNotFoundError:
        # Windows/macOS compatibility
        print("Pipeline commands not available on this platform", file=sys.stderr)

```
