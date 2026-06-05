---
language: r
tags: [forcats, factors, fct_reorder, fct_relevel, fct_lump, fct_infreq, ordered]
title: Factors & Forcats
description: forcats (tidyverse) makes factor manipulation easy. fct_reorder reorders by another variable, fct_relevel moves levels, fct_lump collapses rare levels, fct_infreq orders by frequency, ordered factors.
source: pattern
---

```r
library(forcats)
library(ggplot2)
library(dplyr)

# =====================
# Factor creation
# =====================
colors <- factor(c("red", "blue", "green", "blue", "red"))
levels(colors)   # "blue" "green" "red"

# Explicit level ordering
colors <- factor(c("red", "blue", "green"),
                 levels = c("red", "green", "blue"))

# =====================
# fct_relevel — reorder manually
# =====================
fct_relevel(colors, "blue", after = 0)
fct_relevel(colors, "red", after = Inf)

# =====================
# fct_infreq — order by frequency
# =====================
sizes <- factor(c("M", "L", "S", "M", "L", "M", "XL"))
fct_infreq(sizes) |> table()

# =====================
# fct_reorder — reorder by another variable
# =====================
df <- tibble(
  region = factor(c("North", "South", "East", "West",
                     "North", "South", "East", "West")),
  sales  = c(100, 200, 150, 180, 90, 210, 140, 190)
)

df %>%
  mutate(region = fct_reorder(region, sales, .fun = median)) %>%
  ggplot(aes(x = region, y = sales)) +
  geom_boxplot()

# =====================
# fct_lump — lump rare levels together
# =====================
grades <- factor(c(rep("A", 50), rep("B", 30), rep("C", 15),
                   rep("D", 3), rep("F", 2)))
fct_lump(grades, n = 3)        # keep top 3, rest -> "Other"
fct_lump(grades, prop = 0.1)   # keep levels with >= 10% of total
fct_lump_min(grades, min = 10) # keep levels with count >= 10

# =====================
# fct_recode — rename factor levels
# =====================
x <- factor(c("a", "b", "c"))
fct_recode(x, apple = "a", banana = "b")

# =====================
# Ordered factors
# =====================
ordered(c("low", "medium", "high"),
        levels = c("low", "medium", "high"))

# =====================
# Other useful
# =====================
fct_drop(colors)
fct_expand(colors, "yellow")
fct_collapse(colors,
             warm = c("red", "orange"),
             cool = c("blue", "green"))
fct_count(colors)

```
