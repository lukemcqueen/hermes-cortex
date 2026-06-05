---
language: python
tags: [algorithm, search]
title: Binary Search
description: Binary search on a sorted array. O(log n). Returns index or -1.
source: textbook
---

```python
def binary_search(arr, target):
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1

```
