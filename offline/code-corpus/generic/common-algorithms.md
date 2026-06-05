---
language: generic
tags: [algorithm]
title: Common Algorithms Reference
description: Quick reference for common algorithm complexities and patterns.
source: reference
---

```generic
# Algorithm Complexity Reference

## Sorting
| Algorithm    | Best    | Average | Worst   | Space  | Stable |
|-------------|---------|---------|---------|--------|--------|
| Quick Sort  | O(n log n) | O(n log n) | O(n²) | O(log n) | No  |
| Merge Sort  | O(n log n) | O(n log n) | O(n log n) | O(n) | Yes |
| Heap Sort   | O(n log n) | O(n log n) | O(n log n) | O(1) | No  |
| Insertion   | O(n)    | O(n²)   | O(n²)   | O(1)   | Yes |
| Bubble      | O(n)    | O(n²)   | O(n²)   | O(1)   | Yes |

## Search
| Algorithm         | Time       | Space  | Requires |
|------------------|------------|--------|----------|
| Linear Search    | O(n)       | O(1)   | Nothing  |
| Binary Search    | O(log n)   | O(1)   | Sorted   |
| BFS (graph)      | O(V + E)   | O(V)   | Graph    |
| DFS (graph)      | O(V + E)   | O(V)   | Graph    |
| Dijkstra         | O(E log V) | O(V)   | + weights|
| A*               | O(E)       | O(V)   | Heuristic|

## Data Structures
| Structure    | Access | Search | Insert | Delete |
|-------------|--------|--------|--------|--------|
| Array       | O(1)   | O(n)   | O(n)   | O(n)   |
| Linked List | O(n)   | O(n)   | O(1)   | O(1)   |
| Hash Table  | O(1)   | O(1)   | O(1)   | O(1)   |
| BST (balanced) | O(log n) | O(log n) | O(log n) | O(log n) |
| Heap        | O(1)¹  | O(n)   | O(log n) | O(log n) |
¹ Only min/max
```
