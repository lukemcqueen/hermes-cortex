---
language: go
tags: [go, cli, cobra, viper]
title: Building CLI Apps with Cobra
description: Cobra root command, subcommands, flags, viper integration, and custom help templates
source: pattern
---

# Building CLI Apps with Cobra

Cobra is the standard CLI framework for Go applications (used by Kubernetes,
Hugo, and Docker). This covers the full workflow from scaffold to production.

## Project Setup

```shell
mkdir -p mycli/cmd
cd mycli
go mod init github.com/user/mycli
go get github.com/spf13/cobra
go get github.com/spf13/viper
```

## Scaffolding with Cobra CLI (Optional)

```shell
# Install cobra-cli
go install github.com/spf13/cobra-cli@latest

# Initialize a new CLI project
cobra-cli init --author "Your Name" --viper

# Add subcommands
cobra-cli add serve
cobra-cli add config
cobra-cli add version
```

## Root Command

```go
// cmd/root.go
package cmd

import (
    "fmt"
    "os"

    "github.com/spf13/cobra"
    "github.com/spf13/viper"
)

var (
    cfgFile     string
    verbose     bool
    outputFormat string
)

var rootCmd = &cobra.Command{
    Use:   "mycli",
    Short: "MyCLI — a demonstration CLI application",
    Long: `MyCLI is a sample CLI built with Cobra and Viper.
It demonstrates patterns for command structure, flag parsing,
configuration management, and help customization.`,
    PersistentPreRun: func(cmd *cobra.Command, args []string) {
        if verbose {
            fmt.Fprintf(os.Stderr, "verbose: enabled\n")
        }
    },
    RunE: func(cmd *cobra.Command, args []string) error {
        // Default: show help if no subcommand is given
        return cmd.Help()
    },
}

func Execute() {
    err := rootCmd.Execute()
    if err != nil {
        os.Exit(1)
    }
}

func init() {
    cobra.OnInitialize(initConfig)

    // Persistent flags — available to all subcommands
    rootCmd.PersistentFlags().StringVar(&cfgFile, "config", "", "config file (default: $HOME/.mycli.yaml)")
    rootCmd.PersistentFlags().BoolVarP(&verbose, "verbose", "v", false, "verbose output")
    rootCmd.PersistentFlags().StringVarP(&outputFormat, "output", "o", "text", "output format (text|json|yaml)")

    // Bind flags to viper
    viper.BindPFlag("verbose", rootCmd.PersistentFlags().Lookup("verbose"))
    viper.BindPFlag("output", rootCmd.PersistentFlags().Lookup("output"))
}

func initConfig() {
    if cfgFile != "" {
        viper.SetConfigFile(cfgFile)
    } else {
        home, err := os.UserHomeDir()
        cobra.CheckErr(err)

        viper.AddConfigPath(home)
        viper.AddConfigPath(".")
        viper.SetConfigType("yaml")
        viper.SetConfigName(".mycli")
    }

    viper.AutomaticEnv()
    viper.SetEnvPrefix("MYCLI")

    if err := viper.ReadInConfig(); err == nil {
        fmt.Fprintln(os.Stderr, "Using config file:", viper.ConfigFileUsed())
    }
}
```

## Subcommands

```go
// cmd/serve.go
package cmd

import (
    "fmt"
    "log"
    "net/http"
    "time"

    "github.com/spf13/cobra"
    "github.com/spf13/viper"
)

var (
    servePort    int
    serveHost    string
)

var serveCmd = &cobra.Command{
    Use:   "serve",
    Short: "Start the HTTP server",
    Long: `Starts an HTTP server on the specified host and port.
Configuration can be set via flags, config file, or environment variables.`,
    Example: `  mycli serve --port 8080 --host 0.0.0.0
  mycli serve -p 9090`,
    Args: cobra.NoArgs,
    RunE: func(cmd *cobra.Command, args []string) error {
        port := viper.GetInt("serve.port")
        host := viper.GetString("serve.host")

        addr := fmt.Sprintf("%s:%d", host, port)
        log.Printf("Starting server on %s", addr)

        mux := http.NewServeMux()
        mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
            w.Write([]byte(`{"status":"ok"}`))
        })

        srv := &http.Server{
            Addr:         addr,
            Handler:      mux,
            ReadTimeout:  10 * time.Second,
            WriteTimeout: 10 * time.Second,
        }
        return srv.ListenAndServe()
    },
}

func init() {
    rootCmd.AddCommand(serveCmd)

    serveCmd.Flags().IntVarP(&servePort, "port", "p", 8080, "server port")
    serveCmd.Flags().StringVar(&serveHost, "host", "127.0.0.1", "server host")

    viper.BindPFlag("serve.port", serveCmd.Flags().Lookup("port"))
    viper.BindPFlag("serve.host", serveCmd.Flags().Lookup("host"))
}
```

```go
// cmd/config.go
package cmd

import (
    "fmt"

    "github.com/spf13/cobra"
    "github.com/spf13/viper"
)

var configCmd = &cobra.Command{
    Use:   "config",
    Short: "Manage configuration",
    Long:  "View, set, or get configuration values.",
}

var configGetCmd = &cobra.Command{
    Use:   "get <key>",
    Short: "Get a config value",
    Args:  cobra.ExactArgs(1),
    Run: func(cmd *cobra.Command, args []string) {
        val := viper.Get(args[0])
        fmt.Printf("%s = %v\n", args[0], val)
    },
}

var configSetCmd = &cobra.Command{
    Use:   "set <key> <value>",
    Short: "Set a config value",
    Args:  cobra.ExactArgs(2),
    Run: func(cmd *cobra.Command, args []string) {
        viper.Set(args[0], args[1])
        viper.WriteConfig()
        fmt.Printf("Set %s = %s\n", args[0], args[1])
    },
}

func init() {
    rootCmd.AddCommand(configCmd)
    configCmd.AddCommand(configGetCmd)
    configCmd.AddCommand(configSetCmd)
}
```

```go
// cmd/version.go
package cmd

import (
    "fmt"
    "runtime"

    "github.com/spf13/cobra"
)

// Set via ldflags at build time:
// go build -ldflags "-X cmd.Version=1.0.0 -X cmd.CommitSHA=abc1234"
var (
    Version   = "dev"
    CommitSHA = "none"
    BuildDate = "unknown"
)

var versionCmd = &cobra.Command{
    Use:   "version",
    Short: "Print the version number",
    Run: func(cmd *cobra.Command, args []string) {
        fmt.Printf("mycli %s\n", Version)
        fmt.Printf("commit: %s\n", CommitSHA)
        fmt.Printf("built:  %s\n", BuildDate)
        fmt.Printf("go:     %s %s/%s\n", runtime.Version(), runtime.GOOS, runtime.GOARCH)
    },
}

func init() {
    rootCmd.AddCommand(versionCmd)
}
```

## Main Entry Point

```go
// main.go
package main

import "github.com/user/mycli/cmd"

func main() {
    cmd.Execute()
}
```

## Viper Integration — Config File

```yaml
# .mycli.yaml (at $HOME or project root)
verbose: false
output: json

serve:
  port: 9090
  host: "0.0.0.0"
```

## Custom Help Template

```go
// cmd/root.go — add to init()

func init() {
    // Custom help template
    rootCmd.SetHelpTemplate(`{{.Short}}

Usage:
  {{.Use}} [command] [flags]

Available Commands:{{range .Commands}}{{if .IsAvailableCommand}}
  {{rpad .Name .NamePadding }} {{.Short}}{{end}}{{end}}

Flags:
{{.LocalFlags.FlagUsages | trimTrailingWhitespaces}}

Global Flags:
{{.InheritedFlags.FlagUsages | trimTrailingWhitespaces}}

Use "{{.CommandPath}} [command] --help" for more information about a command.
`)

    // Custom usage template (shown on error)
    rootCmd.SetUsageTemplate(`Usage: {{.Use}} [flags] [command]

Try '{{.CommandPath}} --help' for more information.
`)
}
```

## Advanced Flag Patterns

```go
// cmd/serve.go — init()
func init() {
    rootCmd.AddCommand(serveCmd)

    // Required flag
    serveCmd.Flags().String("required-flag", "", "this flag is required")
    serveCmd.MarkFlagRequired("required-flag")

    // Deprecated flag with message
    serveCmd.Flags().Bool("old-flag", false, "deprecated")
    serveCmd.Flags().MarkDeprecated("old-flag", "use --new-flag instead")

    // Hidden flag (useful for testing)
    serveCmd.Flags().Bool("hidden", false, "internal use")
    serveCmd.Flags().MarkHidden("hidden")

    // Shorthand annotation for help grouping
    serveCmd.Flags().SetAnnotation("port", cobra.BashCompOneRequiredFlag, "true")
}
```

## Build and Run

```shell
# Development
go run . serve --port 8080

# Production build with version injection
go build -ldflags "\
  -X 'cmd.Version=1.0.0' \
  -X 'cmd.CommitSHA=$(git rev-parse --short HEAD)' \
  -X 'cmd.BuildDate=$(date -u +%Y-%m-%dT%H:%M:%SZ)'" \
  -o mycli .

# Cross-compile
GOOS=linux GOARCH=amd64 go build -ldflags "-X 'cmd.Version=1.0.0'" -o mycli-linux-amd64 .
GOOS=darwin GOARCH=arm64 go build -ldflags "-X 'cmd.Version=1.0.0'" -o mycli-darwin-arm64 .
```

## Testing Subcommands

```go
// cmd/serve_test.go
package cmd

import (
    "bytes"
    "testing"
)

func TestServeCmdHelp(t *testing.T) {
    buf := new(bytes.Buffer)
    rootCmd.SetOut(buf)
    rootCmd.SetArgs([]string{"serve", "--help"})

    err := rootCmd.Execute()
    if err != nil {
        t.Fatalf("unexpected error: %v", err)
    }

    output := buf.String()
    if !contains(output, "Start the HTTP server") {
        t.Errorf("expected help text, got:\n%s", output)
    }
}

func TestVersionOutput(t *testing.T) {
    buf := new(bytes.Buffer)
    rootCmd.SetOut(buf)
    rootCmd.SetArgs([]string{"version"})

    err := rootCmd.Execute()
    if err != nil {
        t.Fatalf("unexpected error: %v", err)
    }

    output := buf.String()
    if !contains(output, "mycli") {
        t.Errorf("expected version output, got:\n%s", output)
    }
}

func contains(s, substr string) bool {
    return len(s) >= len(substr) && containsStr(s, substr)
}

func containsStr(s, substr string) bool {
    for i := 0; i <= len(s)-len(substr); i++ {
        if s[i:i+len(substr)] == substr {
            return true
        }
    }
    return false
}
```

## Directory Layout

```
mycli/
├── main.go
├── cmd/
│   ├── root.go
│   ├── serve.go
│   ├── config.go
│   ├── version.go
│   └── serve_test.go
├── .mycli.yaml
├── go.mod
└── go.sum
```

## Common Cobra Validators

```go
cobra.NoArgs                         // error if any args
cobra.ExactArgs(n)                   // exactly n args
cobra.MaximumNArgs(n)                // at most n args
cobra.MinimumNArgs(n)                // at least n args
cobra.RangeArgs(min, max)            // between min and max
cobra.ExactValidArgs(n)              // exactly n and must match ValidArgs
cobra.OnlyValidArgs                  // all args must match ValidArgs
cobra.ArbitraryArgs                  // any args allowed (default for Run)
cobra.MatchAll(cobra.ExactArgs(1), cobra.OnlyValidArgs)  // combined
```