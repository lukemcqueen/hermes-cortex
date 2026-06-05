---
language: r
tags: [ggplot2, ggplot, aes, geom_point, geom_line, geom_bar, geom_histogram, facet_wrap, theme]
title: ggplot2
description: ggplot2 implements the Grammar of Graphics. Start with ggplot() + aes() + geom_*(). Add themes, facets, labels. ggsave() saves to file. Scales control colours, axes, legends.
source: pattern
---

```r
library(ggplot2)

# Basic scatter plot
ggplot(mtcars, aes(x = wt, y = mpg)) +
  geom_point(color = "steelblue", size = 3, alpha = 0.7) +
  labs(title = "MPG vs Weight",
       x = "Weight (1000 lbs)",
       y = "Miles per Gallon") +
  theme_minimal()

# Bar chart
ggplot(diamonds, aes(x = cut)) +
  geom_bar(fill = "tomato") +
  labs(title = "Diamond Cut Distribution") +
  theme_classic()

# Histogram with density overlay
ggplot(faithful, aes(x = eruptions)) +
  geom_histogram(aes(y = after_stat(density)),
                 bins = 30,
                 fill = "skyblue",
                 color = "white") +
  geom_density(color = "darkred", linewidth = 1) +
  labs(title = "Old Faithful Eruption Times")

# Line plot (time series)
df <- data.frame(
  year = 2010:2020,
  value = c(10, 12, 15, 14, 18, 20, 22, 25, 24, 28, 30)
)
ggplot(df, aes(x = year, y = value)) +
  geom_line(color = "green4", linewidth = 1.2) +
  geom_point(color = "darkgreen", size = 3) +
  theme_bw()

# Facets
ggplot(mtcars, aes(x = wt, y = mpg)) +
  geom_point() +
  facet_wrap(~ cyl, scales = "free") +
  theme_light()

# Custom theme
ggplot(mtcars, aes(x = factor(cyl), y = mpg, fill = factor(cyl))) +
  geom_boxplot() +
  scale_fill_brewer(palette = "Set2") +
  theme(
    legend.position = "bottom",
    panel.grid.major.x = element_blank(),
    text = element_text(size = 14)
  ) +
  labs(title = "MPG by Cylinder Count")

```
