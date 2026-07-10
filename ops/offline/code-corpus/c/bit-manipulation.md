---
language: c
tags: [bit-manipulation, bitwise, mask, set-bit, clear-bit, toggle-bit, test-bit]
title: Bit Manipulation
description: Bitwise operators &|^~<<>>, bit masks, and set/clear/toggle/test helper macros.
source: pattern
---

```c
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

```
