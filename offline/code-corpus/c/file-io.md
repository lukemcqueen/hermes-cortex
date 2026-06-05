---
language: c
tags: [file-io, fopen, fclose, fread, fwrite, fprintf, fscanf, binary, errno, perror]
title: File I/O
description: fopen/fclose/fread/fwrite/fprintf/fscanf, binary vs text, and error handling with errno/perror.
source: pattern
---

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

int main(void) {
    const char *path = "_demo_file.txt";
    const char *msg  = "Hello, file!\n42\n";

    /* --- text write --- */
    FILE *fp = fopen(path, "w");
    if (!fp) { perror(path); return 1; }
    fprintf(fp, "%s", msg);
    fclose(fp);

    /* --- text read --- */
    fp = fopen(path, "r");
    if (!fp) { perror(path); return 1; }
    char line[256];
    while (fgets(line, sizeof line, fp)) {
        printf("read: %s", line);
    }
    fclose(fp);

    /* --- binary write --- */
    int arr[] = {1, 2, 3, 4, 5};
    fp = fopen("_demo_bin.bin", "wb");
    if (!fp) { perror("_demo_bin.bin"); return 1; }
    fwrite(arr, sizeof(int), 5, fp);
    fclose(fp);

    /* --- binary read --- */
    int buf[5];
    fp = fopen("_demo_bin.bin", "rb");
    if (!fp) { perror("_demo_bin.bin"); return 1; }
    fread(buf, sizeof(int), 5, fp);
    fclose(fp);
    for (int i = 0; i < 5; i++) printf("%d ", buf[i]);
    printf("\n");

    remove(path);
    remove("_demo_bin.bin");
    return 0;
}

```
