---
language: r
tags: [purrr, map, map_dbl, map_chr, map_df, reduce, keep, discard, walk, compose]
title: purrr & Functional
description: purrr provides functional programming tools: map() variants return different types, reduce() accumulates, keep/discard filter, walk() for side-effects, partial() fixes args, compose() chains functions.
source: pattern
---

```r
library(purrr)

# =====================
# map variants
# =====================
numbers <- list(1, 2, 3, 4, 5)

map(numbers, ~ .x * 2)                  # list(2, 4, 6, 8, 10)
map_dbl(numbers, ~ .x^2)                # double vector: 1, 4, 9, 16, 25
map_chr(numbers, ~ paste("n =", .x))    # character vector
map_lgl(numbers, ~ .x > 3)              # FALSE FALSE FALSE TRUE TRUE

# map_df — returns a data frame (row-binds results)
map_df(1:3, ~ tibble(id = .x, square = .x^2))

# map2 — iterate over two lists in parallel
map2(1:3, 4:6, ~ .x + .y)              # list(5, 7, 9)

# pmap — iterate over multiple lists
pmap(list(a = 1:3, b = 4:6, c = 7:9), ~ ..1 + ..2 + ..3)

# imap — map with index
imap_chr(c(a = "apple", b = "banana"), ~ paste(.y, .x, sep = ": "))

# =====================
# reduce / accumulate
# =====================
reduce(1:5, `+`)                        # 1+2+3+4+5 = 15
reduce(1:5, ~ .x * .y)                  # factorial: 120
accumulate(1:5, `+`)                    # 1, 3, 6, 10, 15

# =====================
# keep / discard / compact
# =====================
x <- list(1, NULL, 2, NA, 3)
compact(x)                              # remove NULL: list(1, 2, NA, 3)

numbers <- c(1, 2, 3, 4, 5)
keep(numbers, ~ .x > 3)                 # 4, 5
discard(numbers, ~ .x %% 2 == 0)        # 1, 3, 5

# =====================
# walk — side effects only
# =====================
walk(c("a", "b", "c"), print)

# =====================
# partial / compose
# =====================
multiply_by <- function(x, y) x * y
double <- partial(multiply_by, y = 2)
double(5)                               # 10

add_one <- ~ .x + 1
square <- ~ .x^2
add_one_then_square <- compose(square, add_one)
add_one_then_square(3)                  # (3+1)^2 = 16

# =====================
# Practical: model fitting with map
# =====================
mtcars %>%
  split(.$cyl) %>%
  map(~ lm(mpg ~ wt, data = .x)) %>%
  map_df(broom::tidy, .id = "cyl")

```
