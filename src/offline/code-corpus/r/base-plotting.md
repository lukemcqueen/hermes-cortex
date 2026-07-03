---
language: r
tags: [base-r, plot, hist, boxplot, par, lines, points, legend, custom-axes]
title: Base R Plotting
description: Base R plotting with plot(), hist(), boxplot(). par() for graphical parameters. lines()/points() overlay. legend() for keys. Custom axes with axis(). Powerful but imperative.
source: pattern
---

```r
# Basic scatter plot
x <- 1:10
y <- rnorm(10, mean = 5, sd = 2)
plot(x, y, main = "Scatter Plot", xlab = "Index", ylab = "Value",
     pch = 19, col = "blue", cex = 1.5)

# Overlay a line
abline(lm(y ~ x), col = "red", lwd = 2)

# Histogram
hist(mtcars$mpg,
     breaks = 10,
     col = "steelblue",
     border = "white",
     main = "Distribution of MPG",
     xlab = "Miles per Gallon")

# Add density curve
hist(mtcars$mpg, breaks = 10, col = "lightgray",
     border = "white", freq = FALSE, main = "MPG with Density")
lines(density(mtcars$mpg), col = "darkred", lwd = 2)

# Boxplot
boxplot(mpg ~ cyl, data = mtcars,
        col = c("red", "green", "blue"),
        main = "MPG by Cylinder",
        xlab = "Cylinders", ylab = "MPG")

# Multiple plots in one device (layout)
par(mfrow = c(2, 2))       # 2x2 grid
plot(mtcars$wt, mtcars$mpg, main = "wt vs mpg")
hist(mtcars$mpg, main = "Histogram")
boxplot(mtcars$hp, main = "HP Boxplot")
plot(mtcars$disp, mtcars$hp, main = "disp vs hp")
par(mfrow = c(1, 1))       # reset

# Custom axes
plot(x, y, xaxt = "n", yaxt = "n", type = "n")
axis(1, at = 1:10, labels = letters[1:10], las = 2)
axis(2, at = seq(0, 10, by = 2), las = 1)
points(x, y, pch = 19, col = "darkgreen")
legend("topleft", legend = "Data points", pch = 19, col = "darkgreen")

```
