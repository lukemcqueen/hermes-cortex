---
language: go
tags: [pattern, concurrency]
title: Channels
description: Buffered/unbuffered channels, select multiplexing, range, close, and directional channel parameters.
source: pattern
---

```go
package main

import (
	"fmt"
	"time"
)

// producer sends values into a send-only channel.
func producer(out chan<- int) {
	for i := 1; i <= 5; i++ {
		fmt.Printf("Producing %d\n", i)
		out <- i
		time.Sleep(100 * time.Millisecond)
	}
	close(out)
}

// consumer reads from a receive-only channel.
func consumer(in <-chan int, done chan<- bool) {
	for val := range in {
		fmt.Printf("Consumed %d\n", val)
	}
	done <- true
}

func main() {
	// Unbuffered channel
	unbuf := make(chan int)
	go func() {
		unbuf <- 42
	}()
	fmt.Println("Unbuffered received:", <-unbuf)

	// Buffered channel
	buf := make(chan string, 3)
	buf <- "a"
	buf <- "b"
	buf <- "c"
	fmt.Println(<-buf, <-buf, <-buf)

	// Channel direction and range
	ch := make(chan int)
	done := make(chan bool)
	go producer(ch)
	go consumer(ch, done)
	<-done

	// Select multiplexing
	c1 := make(chan string, 1)
	c2 := make(chan string, 1)

	c1 <- "one"
	go func() {
		time.Sleep(50 * time.Millisecond)
		c2 <- "two"
	}()

	select {
	case msg := <-c1:
		fmt.Println("From c1:", msg)
	case msg := <-c2:
		fmt.Println("From c2:", msg)
	case <-time.After(100 * time.Millisecond):
		fmt.Println("Timeout")
	}
}

```
