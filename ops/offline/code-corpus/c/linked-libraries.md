---
language: c
tags: [dlopen, dlsym, dlclose, shared-library, static-library, dynamic-loading]
title: Linked Libraries (Static & Dynamic)
description: Static (.a) vs shared (.so) libraries, dlopen/dlsym/dlclose for runtime loading, and link flags.
source: pattern
---

```c
#include <stdio.h>
#include <stdlib.h>
#include <dlfcn.h>
#include <math.h>

/*
 * Static linking:   gcc -c math_ops.c && ar rcs libmath_ops.a math_ops.o
 * Shared linking:   gcc -fPIC -shared -o libmath_ops.so math_ops.c
 * Using static:     gcc main.c -L. -lmath_ops -lm -o app
 * Using shared:     gcc main.c -L. -lmath_ops -o app   (LD_LIBRARY_PATH=.)
 * Runtime loading:  dlopen("libmath_ops.so", RTLD_LAZY)
 */

/* typedef for function pointers we load at runtime */
typedef double (*math_fn_t)(double);

int main(void) {
    /* 1. Normal static/shared linkage via -lm */
    double val = sqrt(49.0);
    printf("sqrt(49) via -lm = %.1f\n", val);

    /* 2. Dynamic loading with dlopen/dlsym */
    void *handle = dlopen("libm.so.6", RTLD_LAZY | RTLD_LOCAL);
    if (!handle) {
        fprintf(stderr, "dlopen error: %s\n", dlerror());
        return 1;
    }

    /* clear existing error */
    dlerror();

    math_fn_t dyn_sin = (math_fn_t)dlsym(handle, "sin");
    char *err = dlerror();
    if (err) {
        fprintf(stderr, "dlsym error: %s\n", err);
        dlclose(handle);
        return 1;
    }

    printf("sin(0.5) via dlsym = %.4f\n", dyn_sin(0.5));

    /* 3. Cleanup */
    dlclose(handle);

    /*
     * Build hints (compile with -ldl for dlopen):
     *   gcc -std=c99 -Wall -o app linked_libraries.c -ldl -lm
     */
    return 0;
}

```
