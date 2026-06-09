---
language: r
tags: [lm, glm, t.test, chisq.test, summary, predict, broom]
title: Statistical Tests & Models
description: R excels at statistics: lm() for linear models, glm() for generalized linear models, t.test(), chisq.test(). summary() for model output. predict() for predictions. broom::tidy for clean output.
source: pattern
---

```r
# =====================
# Linear Model (lm)
# =====================
model <- lm(mpg ~ wt + hp, data = mtcars)
summary(model)                       # coefficients, R-squared, p-values
coef(model)                          # coefficients only
confint(model)                       # confidence intervals

# Predictions
new_data <- data.frame(wt = c(2.5, 3.0), hp = c(100, 150))
predict(model, newdata = new_data)
predict(model, newdata = new_data, interval = "confidence")

# Diagnostics
plot(model)

# =====================
# Generalized Linear Model (glm)
# =====================
glm_model <- glm(am ~ wt + hp, data = mtcars, family = binomial)
summary(glm_model)
predict(glm_model, type = "response")  # probabilities

# =====================
# t-test
# =====================
t.test(mpg ~ am, data = mtcars)                   # two-sample
t.test(mtcars$mpg, mu = 20)                        # one-sample
t.test(mtcars$mpg, mtcars$hp, paired = FALSE)

# =====================
# Chi-squared test
# =====================
tbl <- table(mtcars$cyl, mtcars$am)
chisq.test(tbl)

# =====================
# broom::tidy — clean output
# =====================
library(broom)
tidy(model)                          # coefficient table as tibble
glance(model)                        # model-level stats (R-squared, AIC, etc.)
augment(model)                       # original data + fitted/residuals

# Example workflow
library(broom)
models <- mtcars %>%
  group_by(cyl) %>%
  summarise(model = list(lm(mpg ~ wt, data = pick(everything())))) %>%
  mutate(tidied = map(model, tidy))

```
