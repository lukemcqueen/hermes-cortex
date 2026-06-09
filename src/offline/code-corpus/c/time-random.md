---
language: c
tags: [time, clock, difftime, timespec, rand, srand, high-resolution]
title: Time & Random Numbers
description: time(), clock(), difftime(), rand/srand, and timespec for high-resolution timing.
source: pattern
---

```c
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>  /* usleep — POSIX */

int main(void) {
    /* wall clock time */
    time_t now = time(NULL);
    printf("Current time: %s", ctime(&now));

    /* high-resolution timing */
    struct timespec ts1, ts2;
    clock_gettime(CLOCK_MONOTONIC, &ts1);
    usleep(50000);  /* 50 ms */
    clock_gettime(CLOCK_MONOTONIC, &ts2);

    double elapsed = (ts2.tv_sec - ts1.tv_sec)
                   + (ts2.tv_nsec - ts1.tv_nsec) / 1e9;
    printf("Elapsed: %.6f s\n", elapsed);

    /* CPU time (clock ticks) */
    clock_t start = clock();
    volatile double sum = 0.0;
    for (int i = 0; i < 1000000; i++) sum += i * 0.5;
    clock_t end = clock();
    printf("CPU time: %.3f ms\n",
           1000.0 * (double)(end - start) / CLOCKS_PER_SEC);

    /* difftime */
    time_t later = time(NULL);
    printf("diff: %.0f s\n", difftime(later, now));

    /* random numbers */
    srand((unsigned)now);
    printf("Random [0,99]: %d\n", rand() % 100);

    return 0;
}

```
