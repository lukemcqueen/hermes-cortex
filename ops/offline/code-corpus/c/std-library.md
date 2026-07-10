---
language: c
tags: [stdlib, qsort, bsearch, atoi, atof, rand, srand, abs, printf-format]
title: Standard Library Utilities
description: qsort, bsearch, atoi/atof, rand/srand, abs, and printf format specifiers.
source: pattern
---

```c
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <math.h>

int cmp_int(const void *a, const void *b) {
    return *(const int *)a - *(const int *)b;
}

int main(void) {
    /* qsort */
    int arr[] = {7, 2, 9, 1, 5, 3};
    size_t n = sizeof arr / sizeof arr[0];
    qsort(arr, n, sizeof(int), cmp_int);
    printf("sorted: ");
    for (size_t i = 0; i < n; i++) printf("%d ", arr[i]);
    printf("\n");

    /* bsearch */
    int key = 5;
    int *found = (int *)bsearch(&key, arr, n, sizeof(int), cmp_int);
    printf("bsearch(%d) = %s\n", key, found ? "found" : "not found");

    /* atoi / atof */
    printf("atoi(\"   -42\") = %d\n", atoi("   -42"));
    printf("atof(\"3.1415\") = %f\n", atof("3.1415"));

    /* rand / srand */
    srand((unsigned)time(NULL));
    printf("rand() = %d\n", rand());

    /* abs */
    printf("abs(-7) = %d\n", abs(-7));

    /* printf format specifiers */
    int    i = 255;
    double d = 3.14159265;
    printf("dec=%d  hex=%x  oct=%o  char=%c  str=%s\n", i, i, i, 'A', "hi");
    printf("float=%.2f  sci=%e  g=%g\n", d, d, d);
    printf("padded=|%8d|%-8d|\n", 42, 42);

    return 0;
}

```
