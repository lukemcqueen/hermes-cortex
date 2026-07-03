---
language: c
tags: [preprocessor, macro, define, ifdef, ifndef, pragma-once, line, x-macro]
title: Preprocessor Directives
description: #define macros, #ifdef/#ifndef guards, #pragma once, #line, and the X-macro pattern.
source: pattern
---

```c
#include <stdio.h>

/* constants */
#define PI      3.1415926535
#define RAD2DEG (180.0 / PI)

/* function-like macro */
#define MIN(a, b)  ((a) < (b) ? (a) : (b))
#define MAX(a, b)  ((a) > (b) ? (a) : (b))

/* conditional compilation */
#ifdef DEBUG
#  define LOG(fmt, ...) fprintf(stderr, "[DEBUG] " fmt "\n", ##__VA_ARGS__)
#else
#  define LOG(fmt, ...) /* nothing */
#endif

/* #line directive */
#line 42 "preprocessor.c"

/* X-macro pattern – define a list once and expand it differently */
#define COLORS \
    X(RED,   "red",   0xFF0000) \
    X(GREEN, "green", 0x00FF00) \
    X(BLUE,  "blue",  0x0000FF)

typedef enum {
#define X(id, name, val) id,
    COLORS
#undef X
    COLOR_COUNT
} Color;

static const char *color_names[] = {
#define X(id, name, val) [id] = name,
    COLORS
#undef X
};

static const unsigned color_hex[] = {
#define X(id, name, val) [id] = val,
    COLORS
#undef X
};

/* #pragma once is typically used in headers (not here) */

int main(void) {
    LOG("PI = %f", PI);
    printf("MIN(10,20)=%d   MAX(10,20)=%d\n", MIN(10,20), MAX(10,20));

    for (int i = 0; i < COLOR_COUNT; i++)
        printf("Color %s = #%06X\n", color_names[i], color_hex[i]);

    return 0;
}

```
