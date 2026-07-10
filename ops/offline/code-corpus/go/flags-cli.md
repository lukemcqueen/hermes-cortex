---
language: go
tags: [pattern, cli, util]
title: Flags & CLI
description: Parsing command-line flags with the flag package, os.Args, environment variables, and subcommands.
source: pattern
---

```go
package main

import (
	"flag"
	"fmt"
	"os"
	"strconv"
	"strings"
)

// --- Subcommand-style flag parsing ---

type Config struct {
	Verbose bool
	Output  string
	Count   int
	Port    int
}

func main() {
	// Define flags
	verbose := flag.Bool("v", false, "verbose output")
	output := flag.String("o", "out.txt", "output file path")
	count := flag.Int("n", 1, "number of iterations")
	port := flag.Int("port", 8080, "server port")

	// Custom usage
	flag.Usage = func() {
		fmt.Fprintf(os.Stderr, "Usage: %s [options] [args...]\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "Options:\n")
		flag.PrintDefaults()
	}

	flag.Parse()

	// Populate config
	cfg := Config{
		Verbose: *verbose,
		Output:  *output,
		Count:   *count,
		Port:    *port,
	}

	// Environment override
	if v := os.Getenv("APP_PORT"); v != "" {
		if p, err := strconv.Atoi(v); err == nil {
			cfg.Port = p
		}
	}
	if v := os.Getenv("APP_VERBOSE"); v == "1" || strings.EqualFold(v, "true") {
		cfg.Verbose = true
	}

	// Remaining positional args
	args := flag.Args()

	if cfg.Verbose {
		fmt.Printf("Config: %+v\n", cfg)
		fmt.Printf("Positional args: %v\n", args)
	}

	fmt.Printf("Running on port %d with output %s\n", cfg.Port, cfg.Output)
	for i := 0; i < cfg.Count; i++ {
		fmt.Printf("Iteration %d\n", i+1)
	}
}

```
