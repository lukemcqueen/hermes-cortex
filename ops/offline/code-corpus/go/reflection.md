---
language: go
tags: [pattern, meta]
title: Reflection
description: reflect.TypeOf/ValueOf, Kind inspection, struct tags, dynamic field access and method calls.
source: pattern
---

```go
package main

import (
	"fmt"
	"reflect"
	"strings"
)

type Config struct {
	Host    string `json:"host" env:"APP_HOST" default:"localhost"`
	Port    int    `json:"port" env:"APP_PORT" default:"8080"`
	Debug   bool   `json:"debug" env:"APP_DEBUG" default:"false"`
	Timeout int    `json:"timeout" env:"APP_TIMEOUT" default:"30"`
}

// --- Inspect struct tags ---

func inspectStruct(v interface{}) {
	t := reflect.TypeOf(v)
	if t.Kind() == reflect.Ptr {
		t = t.Elem()
	}

	fmt.Printf("Type: %s\n", t.Name())
	for i := 0; i < t.NumField(); i++ {
		field := t.Field(i)
		fmt.Printf("  Field %d: %s (%s)\n", i, field.Name, field.Type)
		fmt.Printf("    Tag json:  %q\n", field.Tag.Get("json"))
		fmt.Printf("    Tag env:   %q\n", field.Tag.Get("env"))
		fmt.Printf("    Tag default: %q\n", field.Tag.Get("default"))
	}
}

// --- Set defaults from tags ---

func setDefaults(v interface{}) {
	val := reflect.ValueOf(v)
	if val.Kind() != reflect.Ptr || val.IsNil() {
		return
	}
	val = val.Elem()
	t := val.Type()

	for i := 0; i < t.NumField(); i++ {
		field := t.Field(i)
		defaultVal := field.Tag.Get("default")
		if defaultVal == "" {
			continue
		}

		f := val.Field(i)
		if !f.CanSet() {
			continue
		}

		switch f.Kind() {
		case reflect.String:
			if f.String() == "" {
				f.SetString(defaultVal)
			}
		case reflect.Int, reflect.Int64:
			if f.Int() == 0 {
				var v int64
				fmt.Sscanf(defaultVal, "%d", &v)
				f.SetInt(v)
			}
		case reflect.Bool:
			if !f.Bool() && defaultVal == "true" {
				f.SetBool(true)
			}
		}
	}
}

// --- Dynamic method call ---

type Calculator struct{}

func (Calculator) Add(a, b int) int {
	return a + b
}

func (Calculator) Multiply(a, b int) int {
	return a * b
}

func callMethod(obj interface{}, name string, args ...interface{}) []reflect.Value {
	val := reflect.ValueOf(obj)
	method := val.MethodByName(name)
	if !method.IsValid() {
		fmt.Printf("Method %s not found\n", name)
		return nil
	}

	var inputs []reflect.Value
	for _, arg := range args {
		inputs = append(inputs, reflect.ValueOf(arg))
	}

	return method.Call(inputs)
}

// --- Dynamic field read/write ---

func setField(obj interface{}, name string, value interface{}) {
	val := reflect.ValueOf(obj)
	if val.Kind() == reflect.Ptr {
		val = val.Elem()
	}
	field := val.FieldByName(name)
	if !field.IsValid() {
		fmt.Printf("Field %s not found\n", name)
		return
	}
	if field.CanSet() {
		field.Set(reflect.ValueOf(value))
	}
}

func getField(obj interface{}, name string) interface{} {
	val := reflect.ValueOf(obj)
	if val.Kind() == reflect.Ptr {
		val = val.Elem()
	}
	return val.FieldByName(name).Interface()
}

func main() {
	// Inspect struct
	cfg := Config{Host: "example.com"}
	inspectStruct(cfg)

	// Set defaults from tags
	setDefaults(&cfg)
	fmt.Printf("\nAfter defaults: Host=%q Port=%d Debug=%v Timeout=%d\n",
		cfg.Host, cfg.Port, cfg.Debug, cfg.Timeout)

	// Dynamic method call
	calc := Calculator{}
	result := callMethod(calc, "Add", 10, 20)
	if len(result) > 0 {
		fmt.Printf("\n10 + 20 = %v\n", result[0].Interface())
	}

	// Dynamic field access
	setField(&cfg, "Host", "updated.com")
	setField(&cfg, "Port", 9090)
	fmt.Printf("\nAfter dynamic set: Host=%q Port=%d\n",
		getField(&cfg, "Host"), getField(&cfg, "Port"))

	// Kind checking
	var x interface{} = 42
	v := reflect.ValueOf(x)
	fmt.Printf("\nValue: %v, Kind: %s, Type: %s\n", v, v.Kind(), v.Type())

	// Strings check
	_ = strings.Contains("test", "es")
}

```
