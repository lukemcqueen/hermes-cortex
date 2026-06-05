---
language: r
tags: [tidyverse, dplyr, tidyr, group_by, summarise, across, pivot, join]
title: Tidyverse: dplyr & tidyr
description: dplyr's group_by + summarise/across for grouped operations. tidyr's pivot_longer/wider reshape data. separate/unite split/merge columns. Join functions: left_join, inner_join, etc.
source: pattern
---

```r
library(dplyr)
library(tidyr)

# =====================
# Grouped operations
# =====================
df <- tibble(
  group  = rep(c("A", "B"), each = 4),
  gender = rep(c("M", "F"), times = 4),
  value  = c(1, 2, 3, 4, 5, 6, 7, 8)
)

df %>%
  group_by(group, gender) %>%
  summarise(
    avg = mean(value),
    sum = sum(value),
    n   = n(),
    .groups = "drop"
  )

# across — apply function to multiple columns
df %>%
  group_by(group) %>%
  summarise(
    across(where(is.numeric), list(mean = mean, sd = sd)),
    .groups = "drop"
  )

# =====================
# pivot_longer / pivot_wider
# =====================
wide <- tibble(
  id = 1:3,
  a  = c(10, 20, 30),
  b  = c(40, 50, 60)
)

# Wide -> Long
long <- wide %>%
  pivot_longer(cols = c(a, b),
               names_to = "variable",
               values_to = "value")

# Long -> Wide
wide_again <- long %>%
  pivot_wider(names_from = variable,
              values_from = value)

# =====================
# separate / unite
# =====================
df <- tibble(full_name = c("John Smith", "Jane Doe"))
df <- df %>%
  separate(full_name, into = c("first", "last"), sep = " ")
df %>% unite("full_name", first, last, sep = " ")

# =====================
# Joins
# =====================
x <- tibble(id = 1:3, name = c("A", "B", "C"))
y <- tibble(id = c(2, 3, 4), score = c(90, 85, 95))

inner_join(x, y, by = "id")      # rows 2,3 only
left_join(x, y, by = "id")       # all from x, NA for id=1
right_join(x, y, by = "id")      # all from y, NA for id=4
full_join(x, y, by = "id")       # all rows from both
semi_join(x, y, by = "id")       # rows in x that have match in y
anti_join(x, y, by = "id")       # rows in x WITHOUT match in y

```
