---
language: python
tags: [algorithm, graph]
title: Breadth-First Search
description: BFS on a graph using a deque. Returns shortest path distance.
source: textbook
---

```python
from collections import deque

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
    return -1
```
