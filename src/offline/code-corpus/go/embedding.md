---
language: go
tags: [pattern, io, util]
title: Embedding
description: embed.FS with go:embed directive: embedding files, directories, and using embedded FS in tests.
source: pattern
---

```go
package main

import (
	"embed"
	"fmt"
	"io/fs"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"text/template"
	"time"
)

//go:embed static/*
var staticFiles embed.FS

//go:embed config.yaml
var configYAML string

//go:embed templates/*
var templateFS embed.FS

// --- Embedded static file server ---

func main() {
	// Read embedded string
	fmt.Println("=== Embedded config.yaml ===")
	fmt.Println(configYAML[:100], "...")

	fmt.Println("\n=== Embedded file listing ===")
	entries, _ := fs.ReadDir(staticFiles, "static")
	for _, e := range entries {
		info, _ := e.Info()
		fmt.Printf("  %s (%d bytes)\n", e.Name(), info.Size())
	}

	// Read a specific embedded file
	data, _ := staticFiles.ReadFile("static/style.css")
	fmt.Printf("\nstatic/style.css (%d bytes):\n%s\n", len(data), string(data[:100]))

	// Walk embedded directory
	fmt.Println("\n=== Walk embedded FS ===")
	fs.WalkDir(staticFiles, ".", func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		info, _ := d.Info()
		fmt.Printf("  %s (%d bytes)\n", path, info.Size())
		return nil
	})

	// Use embedded templates
	tmpl, _ := template.ParseFS(templateFS, "templates/*.tmpl")
	tmpl.Execute(os.Stdout, map[string]string{"Name": "Alice"})

	// Serve embedded static files via HTTP
	http.Handle("/static/", http.FileServer(http.FS(staticFiles)))
	fmt.Println("\nServing embedded files on :8080/static/")

	// Write embedded files to disk (for init/setup)
	os.WriteFile("out_config.yaml", []byte(configYAML), 0644)

	// --- Extracting embedded files ---
	err := fs.WalkDir(staticFiles, ".", func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			return os.MkdirAll(path, 0755)
		}
		data, err := fs.ReadFile(staticFiles, path)
		if err != nil {
			return err
		}
		return os.WriteFile(path, data, 0644)
	})
	if err != nil {
		log.Fatal(err)
	}
}

//go:embed templates/*.tmpl
var templatesFS embed.FS

// --- Embedded test data ---
var _ = func() struct{} {
	// Verify embedded content at init time
	data, err := templatesFS.ReadFile("templates/base.tmpl")
	if err != nil {
		panic(fmt.Sprintf("missing embedded template: %v", err))
	}
	_ = data
	return struct{}{}
}()

// --- init-time use in tests ---
func loadEmbeddedFixture(name string) ([]byte, error) {
	return staticFiles.ReadFile(filepath.Join("static", name))
}

```
