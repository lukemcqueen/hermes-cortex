---
language: c
tags: [pointers, memory, malloc, calloc, realloc, free, pointer-arithmetic, void-pointer]
title: Pointers & Dynamic Memory
description: Demonstrates malloc/calloc/realloc/free, pointer arithmetic, void pointers, and NULL checks.
source: pattern
---

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(void) {
    /* malloc – uninitialised memory */
    int *p = (int *)malloc(5 * sizeof(int));
    if (!p) { perror("malloc"); return 1; }
    for (int i = 0; i < 5; i++) p[i] = i * 10;

    /* calloc – zero-initialised memory */
    int *q = (int *)calloc(3, sizeof(int));
    if (!q) { perror("calloc"); free(p); return 1; }

    /* realloc – resize */
    int *r = (int *)realloc(p, 10 * sizeof(int));
    if (!r) { perror("realloc"); free(p); free(q); return 1; }
    p = r;   /* reassign on success */

    /* pointer arithmetic */
    printf("p[0]=%d  *(p+3)=%d\n", p[0], *(p + 3));

    /* void pointer */
    void *vp = p;
    printf("via void*: %d\n", ((int *)vp)[4]);

    free(p);
    free(q);
    return 0;
}

```
