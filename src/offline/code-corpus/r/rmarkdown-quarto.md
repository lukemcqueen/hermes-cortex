---
language: r
tags: [rmarkdown, quarto, yaml, code-chunks, inline-r, rendering, parameters]
title: R Markdown / Quarto
description: R Markdown and Quarto blend prose, code, and output. YAML header controls output format. Code chunks with ```{r}. Inline R with `r expr`. Parameterised reports. Render to HTML/PDF/Word.
source: pattern
---

```r
---
title: "My Report"
author: "Data Analyst"
date: "`r Sys.Date()`"
output:
  html_document:
    toc: true
    theme: flatly
  pdf_document:
    toc: true
params:
  data_file: "default.csv"
  threshold: 0.05
---

```{r setup, include=FALSE}
library(tidyverse)
library(knitr)
opts_chunk$set(echo = TRUE, warning = FALSE, message = FALSE)
```

## Introduction

This report analyses data from `r params$data_file`.
The significance threshold is `r params$threshold`.

## Data Loading

```{r data-load}
df <- read_csv(params$data_file)
summary(df)
```

## Analysis

```{r analysis}
model <- lm(value ~ group, data = df)
summary(model)
```

```{r plot}
ggplot(df, aes(x = group, y = value)) +
  geom_boxplot(fill = "steelblue") +
  labs(title = "Values by Group")
```

## Table

```{r table, results='asis'}
kable(anova(model), caption = "ANOVA Table")
```

---

*Rendered on `r Sys.time()`*

```
