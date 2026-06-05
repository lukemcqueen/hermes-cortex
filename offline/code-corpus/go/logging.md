---
language: go
tags: [pattern, util]
title: Logging
description: Standard log package and log/slog structured logging with levels, custom writers, and JSON output.
source: pattern
---

```go
package main

import (
	"bytes"
	"fmt"
	"io"
	"log"
	"log/slog"
	"os"
	"strings"
	"time"
)

// --- Custom log writer ---

type LogWriter struct {
	buf bytes.Buffer
}

func (w *LogWriter) Write(p []byte) (n int, err error) {
	n, err = w.buf.Write(p)
	// Also echo to stdout
	os.Stdout.Write(p)
	return
}

func (w *LogWriter) String() string {
	return w.buf.String()
}

// --- Structured logging with slog ---

func main() {
	// --- Basic log package ---
	log.Println("Basic log message")
	log.SetFlags(log.Ldate | log.Ltime | log.Lshortfile)
	log.Printf("User %s logged in from %s", "alice", "192.168.1.1")

	// Custom writer
	writer := &LogWriter{}
	logger := log.New(writer, "CUSTOM: ", log.LstdFlags)
	logger.Println("This goes to custom writer")
	fmt.Println("Captured:", writer.String())

	// --- slog structured logging ---

	// Default text handler
	slog.Info("Server starting",
		"port", 8080,
		"env", "production",
	)
	slog.Warn("Disk space low",
		"percent", 92.5,
		"mount", "/data",
	)
	slog.Error("Connection refused",
		"host", "db.example.com",
		"port", 5432,
		"retry", 3,
	)

	// JSON handler
	jsonHandler := slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelDebug,
		ReplaceAttr: func(groups []string, a slog.Attr) slog.Attr {
			// Redact sensitive fields
			if a.Key == "password" {
				return slog.String("password", "[REDACTED]")
			}
			return a
		},
	})
	jsonLogger := slog.New(jsonHandler)
	jsonLogger.Debug("Debug message", "key", "value")
	jsonLogger.Info("JSON format",
		"user", "alice",
		"action", "login",
		"password", "secret123", // will be redacted
	)

	// Leveled logging
	slog.SetLogLoggerLevel(slog.LevelWarn)
	slog.Debug("this won't appear") // filtered
	slog.Warn("this will appear")

	// Custom handler that filters and formats
	customHandler := slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
		ReplaceAttr: func(groups []string, a slog.Attr) slog.Attr {
			// Add timestamp in custom format
			if a.Key == "time" {
				if t, ok := a.Value.Any().(time.Time); ok {
					return slog.String("time", t.Format(time.RFC3339))
				}
			}
			return a
		},
	})
	customLogger := slog.New(customHandler)
	customLogger.Info("Custom formatted log", "module", "api")

	// --- Multi-writer ---
	var logBuf bytes.Buffer
	multiWriter := io.MultiWriter(os.Stdout, &logBuf)
	slogger := slog.New(slog.NewTextHandler(multiWriter, nil))
	slogger.Info("Multi-writer test")
	fmt.Println("Buffer contains:", logBuf.String()[:50]+"...")

	// --- Logger with group ---
	groupLogger := slog.With(
		slog.Group("request",
			"id", "req-123",
			"method", "GET",
			"path", "/api/users",
		),
	)
	groupLogger.Info("Request handled", "status", 200)

	// Strings check to suppress "unused" warning
	_ = strings.Contains("test", "es")
}

```
