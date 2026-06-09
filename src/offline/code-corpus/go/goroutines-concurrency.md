---
language: go
tags: [pattern, concurrency]
title: Goroutines & Concurrency
description: Spawning goroutines, sync.WaitGroup for coordination, and goroutine lifecycle management.
source: pattern
---

```go
package main

import (
	"fmt"
	"math/rand"
	"sync"
	"time"
)

// worker simulates processing an item.
func worker(id int, jobs <-chan int, wg *sync.WaitGroup) {
	defer wg.Done()
	for job := range jobs {
		// Simulate work
		delay := time.Duration(rand.Intn(200)) * time.Millisecond
		time.Sleep(delay)
		fmt.Printf("Worker %d processed job %d (took %v)\n", id, job, delay)
	}
}

func main() {
	const numWorkers = 3
	const numJobs = 10

	jobs := make(chan int, numJobs)
	var wg sync.WaitGroup

	// Start workers
	for i := 1; i <= numWorkers; i++ {
		wg.Add(1)
		go worker(i, jobs, &wg)
	}

	// Send jobs
	for j := 1; j <= numJobs; j++ {
		jobs <- j
	}
	close(jobs) // Signals workers no more jobs

	// Wait for all workers to finish
	wg.Wait()
	fmt.Println("All jobs completed.")
}

```
