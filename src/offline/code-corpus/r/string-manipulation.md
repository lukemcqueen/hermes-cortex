---
language: r
tags: [stringr, str_detect, str_replace, str_extract, str_split, str_trim, regex]
title: String Manipulation
description: stringr (tidyverse) provides consistent string functions: str_detect/filter, str_replace/extract, str_split, str_trim, str_pad, str_to_upper/lower. Base R also has grep/gsub/regexpr.
source: pattern
---

```r
library(stringr)

# =====================
# stringr (tidyverse)
# =====================
text <- c("Hello World", "hello R", "Hi there!", "HELLO AGAIN")

# Detect
str_detect(text, "hello")          # FALSE  TRUE FALSE FALSE
str_which(text, "Hello")           # 1 (index)
str_subset(text, "!")              # "Hi there!"

# Replace
str_replace(text, "hello", "bye")           # first match only
str_replace_all(text, "HELLO", "GOODBYE")   # all matches
str_remove(text, "!")                       # remove first match

# Extract
str_extract(text, "[A-Z]+")               # "H" "H" "H" "HELLO"
str_extract_all(text, "[A-Za-z]+")        # list of all words
str_match(text, "(\\w+) (\\w+)")          # captures as matrix

# Split
str_split("a,b,c", ",")                    # list("a", "b", "c")
str_split_fixed("a,b,c", ",", n = 2)      # matrix: "a" "b,c"

# Trim / Pad
str_trim("  padded  ")                    # "padded"
str_pad("7", width = 3, pad = "0")       # "007"

# Case conversion
str_to_upper("hello")                     # "HELLO"
str_to_lower("HELLO")                     # "hello"
str_to_title("hello world")              # "Hello World"

# Length and subset
str_length("hello")                       # 5
str_sub("hello", 2, 4)                    # "ell"

# Regex groups
dates <- c("2024-01-15", "2023-12-25")
str_match(dates, "(\\d{4})-(\\d{2})-(\\d{2})")

# =====================
# Base R equivalents
# =====================
grep("hello", text, value = TRUE)
gsub("hello", "bye", text)
strsplit("a,b,c", ",")
regexpr("hello", text)

```
