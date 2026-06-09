---
language: r
tags: [vectors, c, seq, rep, factors, NA, is.na, na.omit]
title: Vectors & Data Types
description: Vectors are the atomic data type in R. Use c(), seq(), rep() to create them. Factors for categorical data. NA handling: is.na(), na.omit(), na.rm=TRUE.
source: pattern
---

```r
# Vector creation
v1 <- c(1, 2, 3, 4, 5)           # numeric vector
v2 <- c("a", "b", "c")            # character vector
v3 <- c(TRUE, FALSE, TRUE)        # logical vector

# Sequence and repetition
seq(1, 10, by = 2)                # 1 3 5 7 9
1:5                                # 1 2 3 4 5
rep(1:3, times = 2)               # 1 2 3 1 2 3
rep(1:3, each = 2)                # 1 1 2 2 3 3

# Vector types
typeof(v1)                         # "double"
is.numeric(v1)                     # TRUE
is.character(v2)                   # TRUE

# Coercion (all elements become same type)
mixed <- c(1, "two", TRUE)         # all become character: "1", "two", "TRUE"

# Factors — categorical data
gender <- factor(c("M", "F", "F", "M", "F"))
levels(gender)                     # "F" "M"
table(gender)                      # F M  (counts)

# Ordered factor
rating <- ordered(c("low", "high", "medium"),
                   levels = c("low", "medium", "high"))

# NA handling
x <- c(1, 2, NA, 4, NA, 6)
is.na(x)                           # FALSE FALSE TRUE FALSE TRUE FALSE
sum(is.na(x))                      # 2
na.omit(x)                         # removes NA entries (with attributes)
mean(x, na.rm = TRUE)              # (1+2+4+6)/4 = 3.25

# Vectorized operations
v1 <- 1:5
v2 <- 6:10
v1 + v2                            # 7  9 11 13 15
v1^2                               # 1  4  9 16 25
v1 > 3                             # FALSE FALSE FALSE TRUE TRUE

```
