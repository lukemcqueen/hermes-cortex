---
language: python
tags: [async, pattern, net, util]
title: Async/Await Patterns
description: Modern asyncio patterns: asyncio.run, gather, create_task, sleep, Semaphore, and as_completed.
source: pattern
---

```python
import asyncio
import random


async def fetch_url(name: str, delay: float) -> str:
    """Simulate a non-blocking IO operation."""
    await asyncio.sleep(delay)
    return f"Result from {name} (took {delay:.1f}s)"


async def bounded_fetch(sem: asyncio.Semaphore, name: str, delay: float) -> str:
    """Respect a concurrency limit with a Semaphore."""
    async with sem:
        return await fetch_url(name, delay)


async def main() -> None:
    # --- gather: run many tasks concurrently ---
    results = await asyncio.gather(
        fetch_url("alpha", 0.3),
        fetch_url("beta", 0.1),
        fetch_url("gamma", 0.2),
        return_exceptions=True,
    )
    print("Gather results:", results)

    # --- create_task: fire-and-forget with background tracking ---
    background_tasks = set()
    for i in range(3):
        task = asyncio.create_task(fetch_url(f"bg-{i}", random.uniform(0.05, 0.15)))
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

    # --- Semaphore: limit concurrency to 2 ---
    sem = asyncio.Semaphore(2)
    tasks = [bounded_fetch(sem, f"item-{i}", random.uniform(0.1, 0.5)) for i in range(6)]
    for coro in asyncio.as_completed(tasks):
        earliest = await coro
        print("Completed:", earliest)

    # --- wait for all background tasks ---
    if background_tasks:
        await asyncio.wait(background_tasks)

    print("Done")


if __name__ == "__main__":
    asyncio.run(main())

```
