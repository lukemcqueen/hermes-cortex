---
language: go
tags: [pattern, oop]
title: Structs, Methods & Interfaces
description: Go structs with value/pointer receivers, interface satisfaction, and type assertions.
source: pattern
---

```go
package main

import (
	"fmt"
	"math"
)

// --- Interfaces ---

type Shape interface {
	Area() float64
	Perimeter() float64
}

type Describer interface {
	Description() string
}

// --- Structs ---

type Circle struct {
	Radius float64
}

// Value receiver — operates on a copy.
func (c Circle) Area() float64 {
	return math.Pi * c.Radius * c.Radius
}

func (c Circle) Perimeter() float64 {
	return 2 * math.Pi * c.Radius
}

// Pointer receiver — can modify the receiver.
func (c *Circle) Scale(factor float64) {
	c.Radius *= factor
}

func (c Circle) Description() string {
	return fmt.Sprintf("Circle with radius %.2f", c.Radius)
}

type Rectangle struct {
	Width, Height float64
}

func (r Rectangle) Area() float64 {
	return r.Width * r.Height
}

func (r Rectangle) Perimeter() float64 {
	return 2 * (r.Width + r.Height)
}

func (r Rectangle) Description() string {
	return fmt.Sprintf("Rectangle %.2f x %.2f", r.Width, r.Height)
}

// --- Interface satisfaction & type assertion ---

func printShapeInfo(s Shape) {
	// Type assertion to access concrete type
	if desc, ok := s.(Describer); ok {
		fmt.Println(desc.Description())
	}
	fmt.Printf("  Area: %.2f, Perimeter: %.2f\n", s.Area(), s.Perimeter())
}

func main() {
	circle := Circle{Radius: 5}
	rect := Rectangle{Width: 3, Height: 4}

	// Interface slice
	shapes := []Shape{circle, rect}
	for _, s := range shapes {
		printShapeInfo(s)
	}

	// Pointer receiver method
	c := &Circle{Radius: 2}
	c.Scale(3)
	fmt.Printf("Scaled circle area: %.2f\n", c.Area())

	// Empty interface and type switch
	var v interface{} = 42
	switch val := v.(type) {
	case int:
		fmt.Println("int:", val)
	case string:
		fmt.Println("string:", val)
	default:
		fmt.Println("unknown type")
	}
}

```
