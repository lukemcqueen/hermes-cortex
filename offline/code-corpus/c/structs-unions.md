---
language: c
tags: [struct, union, typedef, nested-struct, bit-fields, alignment, packing]
title: Structs, Unions & Bit Fields
description: Struct definitions, typedef, nested structs, union, bit fields, and packed alignment.
source: pattern
---

```c
#include <stdio.h>
#include <stddef.h>
#include <stdint.h>

/* basic struct with typedef */
typedef struct {
    double x, y;
} Point;

/* nested struct */
typedef struct {
    Point top_left;
    Point bottom_right;
} Rect;

/* union – same memory, different interpretations */
union Data {
    int   i;
    float f;
    char  str[4];
};

/* bit fields for flags */
struct Flags {
    unsigned int read   : 1;
    unsigned int write  : 1;
    unsigned int exec   : 1;
    unsigned int unused : 29;
};

/* packed struct – compiler-dependent */
struct __attribute__((packed)) Packed {
    char  c;
    int   i;
    short s;
};

int main(void) {
    Point p = { 1.5, 2.5 };
    printf("Point: (%.1f, %.1f)\n", p.x, p.y);

    Rect r = { {0,0}, {10,10} };
    printf("Rect area = %.0f\n", (r.bottom_right.x - r.top_left.x) *
                                 (r.bottom_right.y - r.top_left.y));

    union Data d;
    d.i = 42;
    printf("union as int: %d, as float: %f\n", d.i, d.f);

    struct Flags f = {1, 1, 0, 0};
    printf("Flags: r=%u w=%u x=%u\n", f.read, f.write, f.exec);

    printf("Packed size = %zu (vs normal %zu)\n",
           sizeof(struct Packed),
           sizeof(char) + sizeof(int) + sizeof(short));

    return 0;
}

```
