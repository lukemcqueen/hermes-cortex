---
language: go
tags: [pattern, util, web]
title: Templates
description: text/template and html/template parsing, execution, template functions, and nested templates.
source: pattern
---

```go
package main

import (
	"bytes"
	"fmt"
	"html/template"
	"os"
	"strings"
	"text/template"
)

// --- Custom template functions ---

var funcMap = template.FuncMap{
	"upper": strings.ToUpper,
	"lower": strings.ToLower,
	"greet": func(name string) string {
		return fmt.Sprintf("Hello, %s!", name)
	},
	"add": func(a, b int) int {
		return a + b
	},
}

// --- Text templates ---

const textTmpl = `
{{- /* This is a comment */ -}}
Report: {{.Title}}
{{- if .Items}}
Items ({{len .Items}}):
{{range .Items}}  - {{.Name | upper}}: {{.Value | printf "$%.2f"}}
{{end}}{{else}}
No items found.
{{end}}
Generated: {{.Generated | dateFormat}}
`

func dateFormat(t string) string {
	return t[:10] // simple formatting helper
}

// --- HTML templates (auto-escaped) ---

const htmlTmpl = `<!DOCTYPE html>
<html>
<head><title>{{.Title}}</title></head>
<body>
	<h1>{{.Title}}</h1>
	{{if .Items}}
	<ul>
	{{range .Items}}
		<li>{{.Name | upper}}: {{.Value | printf "$%.2f"}}</li>
	{{end}}
	</ul>
	{{else}}
	<p>No items.</p>
	{{end}}
	<p>User input: {{.UserInput}}</p>
</body>
</html>`

type Item struct {
	Name  string
	Value float64
}

type Data struct {
	Title     string
	Items     []Item
	Generated string
	UserInput string
}

func main() {
	data := Data{
		Title: "Monthly Report",
		Items: []Item{
			{Name: "widget", Value: 19.99},
			{Name: "gadget", Value: 29.95},
			{Name: "doohickey", Value: 5.00},
		},
		Generated: "2026-06-05T12:00:00Z",
		UserInput: "<script>alert('xss')</script>",
	}

	// --- Text template ---
	tmpl := template.New("report").Funcs(template.FuncMap{
		"dateFormat": dateFormat,
		"upper":      strings.ToUpper,
	})
	tmpl = template.Must(tmpl.Parse(textTmpl))

	var buf bytes.Buffer
	if err := tmpl.Execute(&buf, data); err != nil {
		panic(err)
	}
	fmt.Println("=== TEXT TEMPLATE ===")
	fmt.Println(buf.String())

	// --- HTML template (auto-escaping!) ---
	htmlTmpl := template.Must(template.New("webpage").Funcs(funcMap).Parse(htmlTmpl))

	var htmlBuf bytes.Buffer
	if err := htmlTmpl.Execute(&htmlBuf, data); err != nil {
		panic(err)
	}
	fmt.Println("=== HTML TEMPLATE ===")
	fmt.Println(htmlBuf.String())

	// Write to file
	os.WriteFile("output.html", htmlBuf.Bytes(), 0644)
}

```
