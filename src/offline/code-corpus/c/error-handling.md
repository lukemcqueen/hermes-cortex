---
language: c
tags: [error-handling, errno, perror, strerror, setjmp, longjmp, goto-cleanup]
title: Error Handling Patterns
description: errno/perror/strerror, setjmp/longjmp for non-local recovery, and the goto cleanup pattern.
source: pattern
---

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <setjmp.h>

/* setjmp/longjmp example */
static jmp_buf env;

static void risky(void) {
    if (rand() % 3 == 0)
        longjmp(env, 1);   /* jump back to setjmp */
    puts("risky succeeded");
}

/* goto cleanup pattern */
static int do_work(void) {
    FILE *fp = fopen("_tmp.txt", "w");
    if (!fp) { perror("fopen"); return -1; }

    char *buf = (char *)malloc(1024);
    if (!buf) { perror("malloc"); fclose(fp); return -1; }

    if (fprintf(fp, "data") < 0) {
        goto cleanup;
    }

    /* ... more work ... */
    puts("work done");
    cleanup:
    free(buf);
    fclose(fp);
    return 0;
}

int main(void) {
    /* errno / perror / strerror */
    FILE *f = fopen("/nonexistent", "r");
    if (!f) {
        perror("fopen");
        printf("strerror: %s\n", strerror(errno));
    }

    /* setjmp / longjmp */
    if (setjmp(env) == 0) {
        risky();   /* may longjmp */
    } else {
        printf("recovered from longjmp\n");
    }

    do_work();
    remove("_tmp.txt");
    return 0;
}

```
