---
language: go
tags: [pattern, data-structure]
title: Slices & Maps
description: make, append, copy, delete, sort, range, composite literals, and common slice/map idioms.
source: pattern
---

```go
package main

import (
	"fmt"
	"sort"
)

func main() {
	// --- Composite literals ---
	nums := []int{3, 1, 4, 1, 5, 9, 2, 6}
	grades := map[string]int{
		"Alice": 90,
		"Bob":   85,
		"Carol": 92,
	}

	fmt.Println("nums:", nums)
	fmt.Println("grades:", grades)

	// --- make, append, copy ---
	// make with length and capacity
	s := make([]int, 0, 10)
	s = append(s, 1, 2, 3, 4, 5)
	fmt.Println("slice:", s, "len:", len(s), "cap:", cap(s))

	// append variadic
	s = append(s, []int{6, 7, 8}...)
	fmt.Println("after append:", s)

	// copy
	dest := make([]int, len(s))
	n := copy(dest, s)
	fmt.Printf("copied %d elements: %v\n", n, dest)

	// --- Slice operations ---
	// Sub-slice
	sub := nums[2:5]
	fmt.Println("nums[2:5]:", sub)

	// Delete element (idiomatic)
	i := 2 // index to delete
	nums = append(nums[:i], nums[i+1:]...)
	fmt.Println("after delete index 2:", nums)

	// Filter
	even := nums[:0]
	for _, v := range nums {
		if v%2 == 0 {
			even = append(even, v)
		}
	}
	nums = even
	fmt.Println("filtered even:", nums)

	// --- Map operations ---
	// Check existence
	if grade, ok := grades["Alice"]; ok {
		fmt.Println("Alice's grade:", grade)
	}

	// Delete
	delete(grades, "Bob")
	fmt.Println("after delete Bob:", grades)

	// Iterate over map
	for name, grade := range grades {
		fmt.Printf("  %s: %d\n", name, grade)
	}

	// --- Sorting ---
	strs := []string{"zebra", "apple", "monkey", "dog"}
	sort.Strings(strs)
	fmt.Println("sorted strings:", strs)

	ints := []int{42, 3, 17, 8, 99}
	sort.Ints(ints)
	fmt.Println("sorted ints:", ints)

	// Sort slice of structs
	people := []struct {
		Name string
		Age  int
	}{
		{"Alice", 30},
		{"Bob", 25},
		{"Carol", 35},
	}
	sort.Slice(people, func(i, j int) bool {
		return people[i].Age < people[j].Age
	})
	fmt.Println("sorted by age:", people)

	// Reverse sort
	sort.Sort(sort.Reverse(sort.IntSlice(ints)))
	fmt.Println("reversed ints:", ints)

	// --- Transformations ---
	// Map (transform each element)
	doubled := make([]int, len(nums))
	for i, v := range nums {
		doubled[i] = v * 2
	}
	fmt.Println("doubled:", doubled)

	// Reduce (sum)
	sum := 0
	for _, v := range nums {
		sum += v
	}
	fmt.Println("sum:", sum)
}

```
