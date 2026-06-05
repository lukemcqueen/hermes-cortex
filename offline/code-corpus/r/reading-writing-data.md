---
language: r
tags: [read.csv, read_csv, write_csv, readxl, haven, readRDS, saveRDS]
title: Reading/Writing Data
description: Base R read.csv/write.csv. readr::read_csv/write_csv for faster parsing with better defaults. readxl for Excel, haven for SPSS/Stata/SAS. readRDS/saveRDS for native R objects.
source: pattern
---

```r
# =====================
# CSV files
# =====================

# Base R
df <- read.csv("data.csv", stringsAsFactors = FALSE)
write.csv(df, "output.csv", row.names = FALSE)

# readr (tidyverse) — faster, better defaults
library(readr)
df <- read_csv("data.csv",                # does NOT auto-convert strings to factors
               na = c("", "NA", "NULL"),
               col_types = cols(
                 age = col_double(),
                 name = col_character()
               ))
write_csv(df, "output.csv")
write_csv2(df, "output.csv")              # semicolon separator (EU)

# =====================
# Excel
# =====================
library(readxl)
df <- read_excel("data.xlsx", sheet = 1)
sheets <- excel_sheets("data.xlsx")       # list sheet names

library(writexl)
write_xlsx(df, "output.xlsx")

# =====================
# SAS / SPSS / Stata
# =====================
library(haven)
sas  <- read_sas("data.sas7bdat")
spss <- read_spss("data.sav")
stata <- read_dta("data.dta")
write_dta(stata, "output.dta")

# =====================
# R native format
# =====================
saveRDS(df, "data.rds")
df2 <- readRDS("data.rds")

# Save multiple objects
save(df, df2, file = "data.RData")
load("data.RData")

# =====================
# Other formats
# =====================
# JSON
library(jsonlite)
json <- toJSON(df)
df_from_json <- fromJSON(json)

# Feather (fast, cross-language)
library(feather)
write_feather(df, "data.feather")
df <- read_feather("data.feather")

# Parquet
library(arrow)
write_parquet(df, "data.parquet")
df <- read_parquet("data.parquet")

```
