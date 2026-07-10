---
language: c
tags: [variadic, stdarg, va_list, va_start, va_arg, va_end, vprintf]
title: Variable Arguments (stdarg.h)
description: va_list/va_start/va_arg/va_end for custom variadic functions, and vprintf usage.
source: pattern
---

```c
#include <stdio.h>
#include <stdarg.h>

/* variadic sum */
static int sum(int count, ...) {
    va_list args;
    va_start(args, count);
    int total = 0;
    for (int i = 0; i < count; i++)
        total += va_arg(args, int);
    va_end(args);
    return total;
}

/* variadic print using vprintf */
static void logf(const char *fmt, ...) {
    va_list args;
    va_start(args, fmt);
    vprintf(fmt, args);
    va_end(args);
}

/* variadic error formatting – build string into buffer */
static int format_msg(char *buf, size_t sz, const char *fmt, ...) {
    va_list args;
    va_start(args, fmt);
    int n = vsnprintf(buf, sz, fmt, args);
    va_end(args);
    return n;
}

int main(void) {
    printf("sum(3, 10, 20, 30) = %d\n", sum(3, 10, 20, 30));
    printf("sum(5, 1,2,3,4,5)  = %d\n", sum(5, 1, 2, 3, 4, 5));

    logf("hello from %s, version %d\n", "variadic", 2);

    char buf[256];
    format_msg(buf, sizeof buf, "error code %d at %s:%d", -1, "variadic.c", 42);
    printf("formatted: %s\n", buf);

    return 0;
}

```
