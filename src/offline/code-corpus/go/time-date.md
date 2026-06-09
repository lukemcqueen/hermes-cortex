---
language: go
tags: [pattern, util]
title: Time & Date
description: time.Now, time.Parse/Format, time.Duration, time.Ticker, time.After, and timezone handling.
source: pattern
---

```go
package main

import (
	"fmt"
	"time"
)

func main() {
	// --- Current time ---
	now := time.Now()
	fmt.Println("Now:", now)
	fmt.Println("Unix:", now.Unix())
	fmt.Println("UnixNano:", now.UnixNano())

	// --- Date components ---
	fmt.Printf("Year: %d, Month: %s, Day: %d\n", now.Year(), now.Month(), now.Day())
	fmt.Printf("Hour: %d, Minute: %d, Second: %d\n", now.Hour(), now.Minute(), now.Second())
	fmt.Println("Weekday:", now.Weekday())

	// --- Parsing ---
	// Go uses a reference time: Mon Jan 2 15:04:05 MST 2006
	parsed, err := time.Parse("2006-01-02", "2026-06-05")
	if err != nil {
		panic(err)
	}
	fmt.Println("Parsed date:", parsed)

	parsed2, _ := time.Parse(time.RFC3339, "2026-06-05T15:04:05Z")
	fmt.Println("Parsed RFC3339:", parsed2)

	// Flexible parsing using multiple layouts
	formats := []string{
		"2006-01-02",
		"2006-01-02T15:04:05Z07:00",
		time.RFC1123,
		"Jan 2, 2006",
	}
	for _, layout := range formats {
		if t, err := time.Parse(layout, "Jun 5, 2026"); err == nil {
			fmt.Printf("Matched layout %q: %v\n", layout, t)
		}
	}

	// --- Formatting ---
	fmt.Println("Format YYYY-MM-DD:", now.Format("2006-01-02"))
	fmt.Println("Format RFC3339:", now.Format(time.RFC3339))
	fmt.Println("Format custom:", now.Format("Monday, January 2, 2006 at 3:04 PM"))

	// --- Duration ---
	dur := 2*time.Hour + 30*time.Minute + 15*time.Second
	fmt.Println("Duration:", dur)
	fmt.Println("Minutes:", dur.Minutes())
	fmt.Println("Seconds:", dur.Seconds())
	fmt.Println("Milliseconds:", dur.Milliseconds())

	// Add/Subtract
	tomorrow := now.Add(24 * time.Hour)
	fmt.Println("Tomorrow:", tomorrow)
	lastWeek := now.Add(-7 * 24 * time.Hour)
	fmt.Println("Last week:", lastWeek)

	diff := tomorrow.Sub(now)
	fmt.Println("Difference:", diff)

	// --- Time comparison ---
	a := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	b := time.Date(2026, 6, 1, 0, 0, 0, 0, time.UTC)
	fmt.Println("a before b:", a.Before(b))
	fmt.Println("a after b:", a.After(b))
	fmt.Println("a equal b:", a.Equal(b))

	// --- Ticker ---
	ticker := time.NewTicker(100 * time.Millisecond)
	go func() {
		for t := range ticker.C {
			fmt.Println("Tick at:", t.Format("15:04:05.000"))
		}
	}()
	time.Sleep(350 * time.Millisecond)
	ticker.Stop()
	fmt.Println("Ticker stopped")

	// --- Timer / After ---
	time.AfterFunc(50*time.Millisecond, func() {
		fmt.Println("Timer fired!")
	})

	select {
	case <-time.After(100 * time.Millisecond):
		fmt.Println("100ms timeout elapsed")
	}

	// --- Timezone ---
	loc, _ := time.LoadLocation("America/New_York")
	nyTime := now.In(loc)
	fmt.Println("New York time:", nyTime)

	utcTime := now.UTC()
	fmt.Println("UTC time:", utcTime)
}

```
