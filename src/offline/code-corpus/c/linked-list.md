---
language: c
tags: [linked-list, dynamic-memory, malloc, free, traversal, insertion, deletion]
title: Singly-Linked List
description: Singly-linked list with dynamic memory: insertion, deletion, traversal, and full deallocation.
source: pattern
---

```c
#include <stdio.h>
#include <stdlib.h>

typedef struct Node {
    int          data;
    struct Node *next;
} Node;

Node *list_new(int data) {
    Node *n = (Node *)malloc(sizeof(Node));
    if (!n) return NULL;
    n->data = data;
    n->next = NULL;
    return n;
}

void list_push_front(Node **head, int data) {
    Node *n = list_new(data);
    if (!n) return;
    n->next = *head;
    *head = n;
}

void list_push_back(Node **head, int data) {
    Node *n = list_new(data);
    if (!n) return;
    if (!*head) { *head = n; return; }
    Node *cur = *head;
    while (cur->next) cur = cur->next;
    cur->next = n;
}

int list_pop_front(Node **head, int *out) {
    if (!*head) return -1;
    Node *tmp = *head;
    *out = tmp->data;
    *head = tmp->next;
    free(tmp);
    return 0;
}

void list_free(Node **head) {
    Node *cur = *head;
    while (cur) {
        Node *tmp = cur;
        cur = cur->next;
        free(tmp);
    }
    *head = NULL;
}

void list_print(const Node *head) {
    for (; head; head = head->next)
        printf("%d -> ", head->data);
    printf("NULL\n");
}

int main(void) {
    Node *list = NULL;
    list_push_front(&list, 10);
    list_push_front(&list, 20);
    list_push_back(&list, 30);
    list_print(list);

    int val;
    if (list_pop_front(&list, &val) == 0)
        printf("popped: %d\n", val);
    list_print(list);

    list_free(&list);
    return 0;
}

```
