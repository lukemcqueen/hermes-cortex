---
language: python
tags: [data-structure]
title: Singly Linked List
description: Basic linked list with push, pop, reverse, and traversal.
source: textbook
---

```python
class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next

class LinkedList:
    def __init__(self):
        self.head = None

    def push(self, val):
        node = ListNode(val, self.head)
        self.head = node

    def pop(self):
        if not self.head:
            raise IndexError('empty list')
        val = self.head.val
        self.head = self.head.next
        return val

    def reverse(self):
        prev, curr = None, self.head
        while curr:
            nxt = curr.next
            curr.next = prev
            prev, curr = curr, nxt
        self.head = prev

    def to_list(self):
        result = []
        curr = self.head
        while curr:
            result.append(curr.val)
            curr = curr.next
        return result

```
