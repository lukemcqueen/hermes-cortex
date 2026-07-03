---
language: go
tags: [pattern, test]
title: Testing & Benchmarks
description: Go test patterns: table-driven tests, subtests, helper assertions, and benchmarks with b *testing.B.
source: pattern
---

```go
package main

import (
	"errors"
	"sort"
	"strings"
	"testing"
)

// --- Functions to test ---

func Sum(nums []int) int {
	total := 0
	for _, n := range nums {
		total += n
	}
	return total
}

func FilterEven(nums []int) []int {
	var result []int
	for _, n := range nums {
		if n%2 == 0 {
			result = append(result, n)
		}
	}
	return result
}

func Reverse(s string) (string, error) {
	if s == "" {
		return "", errors.New("empty string")
	}
	runes := []rune(s)
	for i, j := 0, len(runes)-1; i < j; i, j = i+1, j-1 {
		runes[i], runes[j] = runes[j], runes[i]
	}
	return string(runes), nil
}

// --- Table-driven tests ---

func TestSum(t *testing.T) {
	tests := []struct {
		name string
		nums []int
		want int
	}{
		{"empty", nil, 0},
		{"single", []int{5}, 5},
		{"multiple", []int{1, 2, 3, 4, 5}, 15},
		{"negatives", []int{-1, -2, -3}, -6},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := Sum(tt.nums)
			if got != tt.want {
				t.Errorf("Sum(%v) = %d; want %d", tt.nums, got, tt.want)
			}
		})
	}
}

func TestFilterEven(t *testing.T) {
	got := FilterEven([]int{1, 2, 3, 4, 5, 6})
	want := []int{2, 4, 6}
	if !equalSlice(got, want) {
		t.Errorf("FilterEven = %v; want %v", got, want)
	}
}

func TestReverse(t *testing.T) {
	tests := []struct {
		input string
		want  string
		err   bool
	}{
		{"hello", "olleh", false},
		{"a", "a", false},
		{"", "", true},
	}
	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			got, err := Reverse(tt.input)
			if (err != nil) != tt.err {
				t.Fatalf("Reverse(%q) error = %v; want error=%v", tt.input, err, tt.err)
			}
			if got != tt.want {
				t.Errorf("Reverse(%q) = %q; want %q", tt.input, got, tt.want)
			}
		})
	}
}

// --- Helper ---

func equalSlice(a, b []int) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

// --- Benchmark ---

func BenchmarkSum(b *testing.B) {
	nums := []int{1, 2, 3, 4, 5, 10, 20, 30, 40, 50}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		Sum(nums)
	}
}

func BenchmarkSortStrings(b *testing.B) {
	data := []string{"zebra", "apple", "monkey", "dog", "cat"}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		sort.Strings(data)
	}
}

func BenchmarkStringConcat(b *testing.B) {
	parts := []string{"a", "b", "c", "d", "e", "f", "g", "h"}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		var s string
		for _, p := range parts {
			s += p
		}
		_ = s
	}
}

func BenchmarkStringBuilder(b *testing.B) {
	parts := []string{"a", "b", "c", "d", "e", "f", "g", "h"}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		var sb strings.Builder
		for _, p := range parts {
			sb.WriteString(p)
		}
		_ = sb.String()
	}
}

```
