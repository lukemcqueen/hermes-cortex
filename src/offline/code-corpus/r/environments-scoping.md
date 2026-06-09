---
language: r
tags: [environments, scoping, parent.env, assign, get, exists, ls, lockEnvironment, sys.frame]
title: Environments & Scoping
description: R uses lexical scoping. Environments are hash maps with a parent pointer. parent.env chains lookups. assign/get for dynamic access. lockEnvironment prevents modification. sys.frame for call frames.
source: pattern
---

```r
# =====================
# Environment basics
# =====================
e <- new.env(parent = emptyenv())
e$x <- 42
e$y <- "hello"
assign("z", TRUE, envir = e)

get("x", envir = e)                     # 42
exists("y", envir = e)                  # TRUE
ls(e)                                   # "x" "y" "z"

parent.env(e)                           # emptyenv()
parent.env(globalenv())

# =====================
# Lexical scoping demonstration
# =====================
x <- "global"

f <- function() {
  x <- "local to f"
  g <- function() {
    x <- "local to g"
    x   # returns "local to g"
  }
  g()
}

f()                                     # "local to g"

# =====================
# Closure — function captures its enclosing environment
# =====================
make_counter <- function() {
  count <- 0
  function() {
    count <<- count + 1      # <<- assigns in parent environment
    count
  }
}

counter <- make_counter()
counter()                               # 1
counter()                               # 2

# =====================
# assign / get — dynamic variable access
# =====================
for (i in 1:3) {
  assign(paste0("var_", i), i * 10)
}
var_1                                   # 10
var_2                                   # 20
var_3                                   # 30

# =====================
# lockEnvironment — freeze an environment
# =====================
locked <- new.env()
locked$a <- 1
lockEnvironment(locked)

# =====================
# sys.frame — inspect call stack
# =====================
stack_walk <- function() {
  for (i in sys.nframe():1) {
    cat("Frame", i, ": ", deparse(sys.call(i)), "\n", sep = "")
  }
}

outer <- function() {
  middle <- function() {
    inner <- function() {
      stack_walk()
    }
    inner()
  }
  middle()
}

outer()

```
