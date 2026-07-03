---
language: c
tags: [command-line, argc, argv, getopt, option-parsing, --help]
title: Command-Line Arguments
description: argc/argv access, getopt for option parsing, and --help usage display.
source: pattern
---

```c
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>  /* getopt */
#include <string.h>

static void usage(const char *prog) {
    fprintf(stderr,
        "Usage: %s [OPTIONS] [file...]\n"
        "Options:\n"
        "  -v          Verbose\n"
        "  -n NUM      Set count (default: 1)\n"
        "  -h          Show this help\n",
        prog);
}

int main(int argc, char *argv[]) {
    int verbose = 0;
    int ncount  = 1;
    int opt;

    while ((opt = getopt(argc, argv, "vn:h")) != -1) {
        switch (opt) {
        case 'v': verbose = 1;           break;
        case 'n': ncount = atoi(optarg); break;
        case 'h':
        default:  usage(argv[0]);        return (opt == 'h') ? 0 : 1;
        }
    }

    if (verbose)
        printf("verbose mode, ncount=%d\n", ncount);

    for (int i = optind; i < argc; i++)
        printf("file: %s\n", argv[i]);

    if (argc == 1) {
        usage(argv[0]);
    }
    return 0;
}

```
