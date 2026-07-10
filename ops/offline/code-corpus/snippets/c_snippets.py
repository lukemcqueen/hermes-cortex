"""
C language snippet collection — 18 entries covering core C patterns.
Each entry is a 7-tuple:
  (rel_path, language, tags, title, description, source, code)
"""

SNIPPETS = [
    # ──────────────────────────────────────────────────────────────────
    # 1. Pointers & Memory
    # ──────────────────────────────────────────────────────────────────
    (
        "c/pointers-memory.md",
        "c",
        ["pointers", "memory", "malloc", "calloc", "realloc", "free", "pointer-arithmetic", "void-pointer"],
        "Pointers & Dynamic Memory",
        "Demonstrates malloc/calloc/realloc/free, pointer arithmetic, void pointers, and NULL checks.",
        "pattern",
        r"""
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
""",
    ),

    # ──────────────────────────────────────────────────────────────────
    # 2. Arrays & Strings
    # ──────────────────────────────────────────────────────────────────
    (
        "c/arrays-strings.md",
        "c",
        ["arrays", "strings", "char-array", "null-terminated", "strcpy", "strcat", "strlen", "strcmp", "snprintf"],
        "Arrays & Strings",
        "Char arrays, null-terminated strings, strcpy/strcat/strlen/strcmp, and safe snprintf usage.",
        "pattern",
        r"""
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
""",
    ),

    # ──────────────────────────────────────────────────────────────────
    # 3. Functions & Scope
    # ──────────────────────────────────────────────────────────────────
    (
        "c/functions-scope.md",
        "c",
        ["functions", "scope", "static", "inline", "recursion", "function-pointers"],
        "Functions & Scope",
        "Function declaration/definition, static linkage, inline functions, recursion, and function pointers.",
        "pattern",
        r"""
#include <stdio.h>

/* declaration (prototype) */
int add(int a, int b);

/* static function – file scope only */
static void greet(const char *name) {
    printf("Hello, %s!\n", name);
}

/* inline function hint */
static inline int square(int x) {
    return x * x;
}

/* recursion – factorial */
unsigned long fact(unsigned n) {
    return n <= 1 ? 1UL : n * fact(n - 1);
}

int add(int a, int b) { return a + b; }

int main(void) {
    greet("C Programmer");

    printf("add(3,4)=%d\n", add(3, 4));
    printf("square(5)=%d\n", square(5));
    printf("fact(10)=%lu\n", fact(10));

    /* function pointer */
    int (*op)(int, int) = add;
    printf("via fn ptr: op(7,8)=%d\n", op(7, 8));

    return 0;
}
""",
    ),

    # ──────────────────────────────────────────────────────────────────
    # 4. Structs & Unions
    # ──────────────────────────────────────────────────────────────────
    (
        "c/structs-unions.md",
        "c",
        ["struct", "union", "typedef", "nested-struct", "bit-fields", "alignment", "packing"],
        "Structs, Unions & Bit Fields",
        "Struct definitions, typedef, nested structs, union, bit fields, and packed alignment.",
        "pattern",
        r"""
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
""",
    ),

    # ──────────────────────────────────────────────────────────────────
    # 5. File I/O
    # ──────────────────────────────────────────────────────────────────
    (
        "c/file-io.md",
        "c",
        ["file-io", "fopen", "fclose", "fread", "fwrite", "fprintf", "fscanf", "binary", "errno", "perror"],
        "File I/O",
        "fopen/fclose/fread/fwrite/fprintf/fscanf, binary vs text, and error handling with errno/perror.",
        "pattern",
        r"""
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
""",
    ),

    # ──────────────────────────────────────────────────────────────────
    # 6. Dynamic Memory & Linked Lists
    # ──────────────────────────────────────────────────────────────────
    (
        "c/linked-list.md",
        "c",
        ["linked-list", "dynamic-memory", "malloc", "free", "traversal", "insertion", "deletion"],
        "Singly-Linked List",
        "Singly-linked list with dynamic memory: insertion, deletion, traversal, and full deallocation.",
        "pattern",
        r"""
#include <stdio.h>
#include <stdlib.h>

typedef struct Node {
    int          data;
    struct Node *next;
} Node;

Node *list_new(int data) {
    Node *n = (Node *)malloc(sizeof(Node));
    if (!n) return NULL;
    n->data = data;
    n->next = NULL;
    return n;
}

void list_push_front(Node **head, int data) {
    Node *n = list_new(data);
    if (!n) return;
    n->next = *head;
    *head = n;
}

void list_push_back(Node **head, int data) {
    Node *n = list_new(data);
    if (!n) return;
    if (!*head) { *head = n; return; }
    Node *cur = *head;
    while (cur->next) cur = cur->next;
    cur->next = n;
}

int list_pop_front(Node **head, int *out) {
    if (!*head) return -1;
    Node *tmp = *head;
    *out = tmp->data;
    *head = tmp->next;
    free(tmp);
    return 0;
}

void list_free(Node **head) {
    Node *cur = *head;
    while (cur) {
        Node *tmp = cur;
        cur = cur->next;
        free(tmp);
    }
    *head = NULL;
}

void list_print(const Node *head) {
    for (; head; head = head->next)
        printf("%d -> ", head->data);
    printf("NULL\n");
}

int main(void) {
    Node *list = NULL;
    list_push_front(&list, 10);
    list_push_front(&list, 20);
    list_push_back(&list, 30);
    list_print(list);

    int val;
    if (list_pop_front(&list, &val) == 0)
        printf("popped: %d\n", val);
    list_print(list);

    list_free(&list);
    return 0;
}
""",
    ),

    # ──────────────────────────────────────────────────────────────────
    # 7. Preprocessor
    # ──────────────────────────────────────────────────────────────────
    (
        "c/preprocessor.md",
        "c",
        ["preprocessor", "macro", "define", "ifdef", "ifndef", "pragma-once", "line", "x-macro"],
        "Preprocessor Directives",
        "#define macros, #ifdef/#ifndef guards, #pragma once, #line, and the X-macro pattern.",
        "pattern",
        r"""
#include <stdio.h>

/* constants */
#define PI      3.1415926535
#define RAD2DEG (180.0 / PI)

/* function-like macro */
#define MIN(a, b)  ((a) < (b) ? (a) : (b))
#define MAX(a, b)  ((a) > (b) ? (a) : (b))

/* conditional compilation */
#ifdef DEBUG
#  define LOG(fmt, ...) fprintf(stderr, "[DEBUG] " fmt "\n", ##__VA_ARGS__)
#else
#  define LOG(fmt, ...) /* nothing */
#endif

/* #line directive */
#line 42 "preprocessor.c"

/* X-macro pattern – define a list once and expand it differently */
#define COLORS \
    X(RED,   "red",   0xFF0000) \
    X(GREEN, "green", 0x00FF00) \
    X(BLUE,  "blue",  0x0000FF)

typedef enum {
#define X(id, name, val) id,
    COLORS
#undef X
    COLOR_COUNT
} Color;

static const char *color_names[] = {
#define X(id, name, val) [id] = name,
    COLORS
#undef X
};

static const unsigned color_hex[] = {
#define X(id, name, val) [id] = val,
    COLORS
#undef X
};

/* #pragma once is typically used in headers (not here) */

int main(void) {
    LOG("PI = %f", PI);
    printf("MIN(10,20)=%d   MAX(10,20)=%d\n", MIN(10,20), MAX(10,20));

    for (int i = 0; i < COLOR_COUNT; i++)
        printf("Color %s = #%06X\n", color_names[i], color_hex[i]);

    return 0;
}
""",
    ),

    # ──────────────────────────────────────────────────────────────────
    # 8. Standard Library
    # ──────────────────────────────────────────────────────────────────
    (
        "c/std-library.md",
        "c",
        ["stdlib", "qsort", "bsearch", "atoi", "atof", "rand", "srand", "abs", "printf-format"],
        "Standard Library Utilities",
        "qsort, bsearch, atoi/atof, rand/srand, abs, and printf format specifiers.",
        "pattern",
        r"""
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
""",
    ),

    # ──────────────────────────────────────────────────────────────────
    # 9. Error Handling
    # ──────────────────────────────────────────────────────────────────
    (
        "c/error-handling.md",
        "c",
        ["error-handling", "errno", "perror", "strerror", "setjmp", "longjmp", "goto-cleanup"],
        "Error Handling Patterns",
        "errno/perror/strerror, setjmp/longjmp for non-local recovery, and the goto cleanup pattern.",
        "pattern",
        r"""
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
""",
    ),

    # ──────────────────────────────────────────────────────────────────
    # 10. Command-Line Args
    # ──────────────────────────────────────────────────────────────────
    (
        "c/command-line.md",
        "c",
        ["command-line", "argc", "argv", "getopt", "option-parsing", "--help"],
        "Command-Line Arguments",
        "argc/argv access, getopt for option parsing, and --help usage display.",
        "pattern",
        r"""
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
""",
    ),

    # ──────────────────────────────────────────────────────────────────
    # 11. Bit Manipulation
    # ──────────────────────────────────────────────────────────────────
    (
        "c/bit-manipulation.md",
        "c",
        ["bit-manipulation", "bitwise", "mask", "set-bit", "clear-bit", "toggle-bit", "test-bit"],
        "Bit Manipulation",
        "Bitwise operators &|^~<<>>, bit masks, and set/clear/toggle/test helper macros.",
        "pattern",
        r"""
#include <stdio.h>
#include <stdint.h>

/* bit helpers */
#define BIT(n)        (1UL << (n))
#define BIT_SET(x, n)  ((x) |=  BIT(n))
#define BIT_CLR(x, n)  ((x) &= ~BIT(n))
#define BIT_TOG(x, n)  ((x) ^=  BIT(n))
#define BIT_ISSET(x,n) (((x) >> (n)) & 1UL)

#define MASK(w)        ((1UL << (w)) - 1UL)

int main(void) {
    uint32_t reg = 0;

    BIT_SET(reg, 3);
    BIT_SET(reg, 5);
    BIT_SET(reg, 8);
    printf("after set: 0x%04X\n", reg);   /* 0x0128 */

    BIT_CLR(reg, 5);
    printf("after clr: 0x%04X\n", reg);   /* 0x0108 */

    BIT_TOG(reg, 0);
    printf("after tog: 0x%04X\n", reg);   /* 0x0109 */

    printf("bit 3 = %d, bit 0 = %d\n",
           BIT_ISSET(reg, 3), BIT_ISSET(reg, 0));

    /* extract bit field */
    uint32_t val = 0xBEEF;
    uint32_t low_nibble = val & MASK(4);
    printf("low nibble of 0x%X = 0x%X\n", val, low_nibble);

    /* shift */
    uint32_t packed = (0xA << 4) | 0xB;
    printf("packed = 0x%X\n", packed);

    return 0;
}
""",
    ),

    # ──────────────────────────────────────────────────────────────────
    # 12. Enums & Constants
    # ──────────────────────────────────────────────────────────────────
    (
        "c/enums-constants.md",
        "c",
        ["enum", "enum-values", "define", "const", "compound-literal"],
        "Enums & Constants",
        "Enum definitions with explicit values, #define constants, const qualifier, and compound literals.",
        "pattern",
        r"""
#include <stdio.h>

/* #define constants */
#define MAX_BUF  4096
#define VERSION  "1.0.0"

/* enum with explicit values */
typedef enum {
    STATUS_OK       = 0,
    STATUS_WARN     = 1,
    STATUS_ERROR    = 2,
    STATUS_FATAL    = 99
} Status;

/* enum as flags (powers of 2) */
enum Flags {
    FLAG_A = 1 << 0,
    FLAG_B = 1 << 1,
    FLAG_C = 1 << 2,
};

/* const-qualified variables */
const double PI   = 3.1415926535;
const char   *app = "MyApp";

/* compound literal (C99) */
struct point { int x, y; };

int main(void) {
    printf("Version: %s  MAX_BUF=%d\n", VERSION, MAX_BUF);

    Status s = STATUS_OK;
    printf("Status value: %d\n", s);

    int flags = FLAG_A | FLAG_C;
    printf("flags = %d (A|C)\n", flags);

    printf("PI = %.4f, app = %s\n", PI, app);

    /* compound literal */
    struct point p = (struct point){ .x = 10, .y = 20 };
    printf("point: (%d, %d)\n", p.x, p.y);

    return 0;
}
""",
    ),

    # ──────────────────────────────────────────────────────────────────
    # 13. Multi-file Projects
    # ──────────────────────────────────────────────────────────────────
    (
        "c/multi-file-projects.md",
        "c",
        ["multi-file", "header-guards", "extern", "static", "global", "makefile"],
        "Multi-file Projects",
        "Header guards, extern declarations, static vs global scope, and a minimal Makefile. Files: main.c, util.h, util.c, Makefile.",
        "pattern",
        r"""
/* ─── util.h ─── */
#ifndef UTIL_H_
#define UTIL_H_

extern int global_counter;     /* defined in util.c */
int    add(int a, int b);      /* function declaration */
double circle_area(double r);

#endif /* UTIL_H_ */

/* ─── util.c ─── */
#include "util.h"
#include <math.h>

int global_counter = 0;

static void log_call(const char *fn) {   /* file-scoped helper */
    global_counter++;
    /* ... */
}

int add(int a, int b) {
    log_call("add");
    return a + b;
}

double circle_area(double r) {
    return M_PI * r * r;
}

/* ─── main.c ─── */
#include <stdio.h>
#include "util.h"

int main(void) {
    printf("add(3,4)=%d\n", add(3, 4));
    printf("area(2.5)=%.2f\n", circle_area(2.5));
    printf("called %d functions\n", global_counter);
    return 0;
}

/* ─── Makefile ─── */
CFLAGS  = -std=c99 -Wall -Wextra -O2
LDFLAGS = -lm

OBJS = main.o util.o

app: $(OBJS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

%.o: %.c util.h
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f *.o app
""",
    ),

    # ──────────────────────────────────────────────────────────────────
    # 14. Input/Output
    # ──────────────────────────────────────────────────────────────────
    (
        "c/input-output.md",
        "c",
        ["input-output", "getchar", "putchar", "scanf", "printf", "fgets", "sscanf"],
        "Console Input/Output",
        "getchar/putchar, scanf/printf families, and safe parsing with fgets/sscanf.",
        "pattern",
        r"""
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
""",
    ),

    # ──────────────────────────────────────────────────────────────────
    # 15. Time & Random
    # ──────────────────────────────────────────────────────────────────
    (
        "c/time-random.md",
        "c",
        ["time", "clock", "difftime", "timespec", "rand", "srand", "high-resolution"],
        "Time & Random Numbers",
        "time(), clock(), difftime(), rand/srand, and timespec for high-resolution timing.",
        "pattern",
        r"""
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
""",
    ),

    # ──────────────────────────────────────────────────────────────────
    # 16. Variable Arguments
    # ──────────────────────────────────────────────────────────────────
    (
        "c/variadic.md",
        "c",
        ["variadic", "stdarg", "va_list", "va_start", "va_arg", "va_end", "vprintf"],
        "Variable Arguments (stdarg.h)",
        "va_list/va_start/va_arg/va_end for custom variadic functions, and vprintf usage.",
        "pattern",
        r"""
#include <stdio.h>
#include <stdarg.h>

/* variadic sum */
static int sum(int count, ...) {
    va_list args;
    va_start(args, count);
    int total = 0;
    for (int i = 0; i < count; i++)
        total += va_arg(args, int);
    va_end(args);
    return total;
}

/* variadic print using vprintf */
static void logf(const char *fmt, ...) {
    va_list args;
    va_start(args, fmt);
    vprintf(fmt, args);
    va_end(args);
}

/* variadic error formatting – build string into buffer */
static int format_msg(char *buf, size_t sz, const char *fmt, ...) {
    va_list args;
    va_start(args, fmt);
    int n = vsnprintf(buf, sz, fmt, args);
    va_end(args);
    return n;
}

int main(void) {
    printf("sum(3, 10, 20, 30) = %d\n", sum(3, 10, 20, 30));
    printf("sum(5, 1,2,3,4,5)  = %d\n", sum(5, 1, 2, 3, 4, 5));

    logf("hello from %s, version %d\n", "variadic", 2);

    char buf[256];
    format_msg(buf, sizeof buf, "error code %d at %s:%d", -1, "variadic.c", 42);
    printf("formatted: %s\n", buf);

    return 0;
}
""",
    ),

    # ──────────────────────────────────────────────────────────────────
    # 17. Socket Programming
    # ──────────────────────────────────────────────────────────────────
    (
        "c/socket-tcp.md",
        "c",
        ["socket", "tcp", "server", "bind", "listen", "accept", "connect", "networking"],
        "TCP Socket Programming",
        "socket/bind/listen/accept/connect — a minimal TCP echo server.",
        "pattern",
        r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>

#define PORT 9090
#define BUF_SIZE 1024

int main(void) {
    int server_fd, client_fd;
    struct sockaddr_in addr;
    int opt = 1;

    server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0) { perror("socket"); return 1; }

    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof opt);

    addr.sin_family      = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port        = htons(PORT);

    if (bind(server_fd, (struct sockaddr *)&addr, sizeof addr) < 0) {
        perror("bind"); close(server_fd); return 1;
    }

    if (listen(server_fd, 5) < 0) {
        perror("listen"); close(server_fd); return 1;
    }
    printf("Echo server on port %d\n", PORT);

    client_fd = accept(server_fd, NULL, NULL);
    if (client_fd < 0) { perror("accept"); close(server_fd); return 1; }

    char buf[BUF_SIZE];
    ssize_t n;
    while ((n = read(client_fd, buf, sizeof buf - 1)) > 0) {
        buf[n] = '\0';
        printf("received: %s", buf);
        write(client_fd, buf, n);
    }

    close(client_fd);
    close(server_fd);
    return 0;
}
""",
    ),

    # ──────────────────────────────────────────────────────────────────
    # 18. Linked Libraries
    # ──────────────────────────────────────────────────────────────────
    (
        "c/linked-libraries.md",
        "c",
        ["dlopen", "dlsym", "dlclose", "shared-library", "static-library", "dynamic-loading"],
        "Linked Libraries (Static & Dynamic)",
        "Static (.a) vs shared (.so) libraries, dlopen/dlsym/dlclose for runtime loading, and link flags.",
        "pattern",
        r"""
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
""",
    ),
]
