---
language: c
tags: [input-output, getchar, putchar, scanf, printf, fgets, sscanf]
title: Console Input/Output
description: getchar/putchar, scanf/printf families, and safe parsing with fgets/sscanf.
source: pattern
---

```c
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

int main(void) {
    /* putchar / getchar */
    printf("Enter a character: ");
    int ch = getchar();
    while (getchar() != '\n');   /* consume rest of line */
    printf("You entered: ");
    putchar(ch);
    putchar('\n');

    /* scanf – basic */
    int i; double d;
    printf("Enter int and double: ");
    if (scanf("%d %lf", &i, &d) == 2) {
        printf("int=%d  double=%.2f\n", i, d);
    }
    while (getchar() != '\n');   /* flush */

    /* fgets / sscanf – safe parsing */
    char line[128];
    printf("Enter three ints: ");
    if (fgets(line, sizeof line, stdin)) {
        int a, b, c;
        if (sscanf(line, "%d %d %d", &a, &b, &c) == 3) {
            printf("sum = %d\n", a + b + c);
        }
    }

    /* formatted output */
    printf("|%-10s|%10s|\n", "left", "right");
    printf("|%*d|\n", 8, 42);

    return 0;
}

```
