---
language: c
tags: [arrays, strings, char-array, null-terminated, strcpy, strcat, strlen, strcmp, snprintf]
title: Arrays & Strings
description: Char arrays, null-terminated strings, strcpy/strcat/strlen/strcmp, and safe snprintf usage.
source: pattern
---

```c
#include <stdio.h>
#include <string.h>

int main(void) {
    char s1[32] = "Hello";
    char s2[]   = " World";

    /* length */
    printf("len(s1)=%zu  len(s2)=%zu\n", strlen(s1), strlen(s2));

    /* concatenation (safe: check buffer) */
    if (strlen(s1) + strlen(s2) + 1 <= sizeof s1) {
        strcat(s1, s2);
    }
    printf("s1 after strcat: \"%s\"\n", s1);

    /* copy */
    char buf[64];
    strcpy(buf, s1);
    printf("buf = \"%s\"\n", buf);

    /* comparison */
    printf("strcmp(\"abc\",\"abd\") = %d\n", strcmp("abc", "abd"));

    /* snprintf – safe formatted string building */
    char fmt[128];
    snprintf(fmt, sizeof fmt, "%s — length = %zu", buf, strlen(buf));
    printf("%s\n", fmt);

    return 0;
}

```
