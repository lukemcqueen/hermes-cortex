---
language: r
tags: [data-frame, tibble, dplyr, filter, select, mutate, arrange, summarise, pipe]
title: Data Frames & Tibbles
description: data.frame and tibble (tidyverse) are the workhorses for tabular data. dplyr verbs: filter/select/mutate/arrange/summarise. The %>% pipe chains operations. Tibbles print nicely and don't auto-convert strings.
source: pattern
---

```r
# Base R data.frame
df <- data.frame(
  name = c("Alice", "Bob", "Charlie"),
  age  = c(25, 30, 35),
  city = c("NYC", "LA", "Chicago"),
  stringsAsFactors = FALSE
)

# Access columns
df$name                            # vector
df[, "age"]                        # column
df[2, ]                            # row 2
df[1:2, c("name", "city")]        # subset rows and columns

# Tibble (tidyverse)
library(tibble)
tbl <- tibble(
  name = c("Alice", "Bob", "Charlie"),
  age  = c(25, 30, 35),
  city = c("NYC", "LA", "Chicago")
)

# dplyr chained with pipe
library(dplyr)

tbl %>%
  filter(age > 28) %>%
  select(name, age) %>%
  mutate(age_group = ifelse(age > 30, "30+", "20-30")) %>%
  arrange(desc(age)) %>%
  summarise(avg_age = mean(age, na.rm = TRUE))

# Adding columns
tbl <- tbl %>%
  mutate(
    age_sq = age^2,
    is_adult = age >= 18
  )

# Rename
tbl %>% rename(full_name = name)

# Distinct rows
tbl %>% distinct(city)

```
