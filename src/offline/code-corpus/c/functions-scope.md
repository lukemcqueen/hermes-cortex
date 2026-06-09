---
language: c
tags: [functions, scope, static, inline, recursion, function-pointers]
title: Functions & Scope
description: Function declaration/definition, static linkage, inline functions, recursion, and function pointers.
source: pattern
---

```c
#include <stdio.h>

/* declaration (prototype) */
int add(int a, int b);

/* static function – file scope only */
static void greet(const char *name) {
    printf("Hello, %s!\n", name);
}

/* inline function hint */
static inline int square(int x) {
    return x * x;
}

/* recursion – factorial */
unsigned long fact(unsigned n) {
    return n <= 1 ? 1UL : n * fact(n - 1);
}

int add(int a, int b) { return a + b; }

int main(void) {
    greet("C Programmer");

    printf("add(3,4)=%d\n", add(3, 4));
    printf("square(5)=%d\n", square(5));
    printf("fact(10)=%lu\n", fact(10));

    /* function pointer */
    int (*op)(int, int) = add;
    printf("via fn ptr: op(7,8)=%d\n", op(7, 8));

    return 0;
}

```
