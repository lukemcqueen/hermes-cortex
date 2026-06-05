---
language: c
tags: [enum, enum-values, define, const, compound-literal]
title: Enums & Constants
description: Enum definitions with explicit values, #define constants, const qualifier, and compound literals.
source: pattern
---

```c
#include <stdio.h>

/* #define constants */
#define MAX_BUF  4096
#define VERSION  "1.0.0"

/* enum with explicit values */
typedef enum {
    STATUS_OK       = 0,
    STATUS_WARN     = 1,
    STATUS_ERROR    = 2,
    STATUS_FATAL    = 99
} Status;

/* enum as flags (powers of 2) */
enum Flags {
    FLAG_A = 1 << 0,
    FLAG_B = 1 << 1,
    FLAG_C = 1 << 2,
};

/* const-qualified variables */
const double PI   = 3.1415926535;
const char   *app = "MyApp";

/* compound literal (C99) */
struct point { int x, y; };

int main(void) {
    printf("Version: %s  MAX_BUF=%d\n", VERSION, MAX_BUF);

    Status s = STATUS_OK;
    printf("Status value: %d\n", s);

    int flags = FLAG_A | FLAG_C;
    printf("flags = %d (A|C)\n", flags);

    printf("PI = %.4f, app = %s\n", PI, app);

    /* compound literal */
    struct point p = (struct point){ .x = 10, .y = 20 };
    printf("point: (%d, %d)\n", p.x, p.y);

    return 0;
}

```
