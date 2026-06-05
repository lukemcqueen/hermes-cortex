---
language: go
tags: [pattern, concurrency]
title: Sync Primitives
description: sync.Mutex, sync.RWMutex, sync.Once, sync.Map, and atomic operations for safe concurrent access.
source: pattern
---

```go
package main

import (
	"fmt"
	"sync"
	"sync/atomic"
	"time"
)

// --- Mutex-guarded counter ---

type SafeCounter struct {
	mu    sync.Mutex
	value int
}

func (c *SafeCounter) Increment() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.value++
}

func (c *SafeCounter) Value() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.value
}

// --- RWMutex for read-heavy workloads ---

type Cache struct {
	mu    sync.RWMutex
	store map[string]string
}

func NewCache() *Cache {
	return &Cache{store: make(map[string]string)}
}

func (c *Cache) Get(key string) (string, bool) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	v, ok := c.store[key]
	return v, ok
}

func (c *Cache) Set(key, value string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.store[key] = value
}

// --- sync.Once for lazy init ---

var (
	config     map[string]string
	configOnce sync.Once
)

func loadConfig() map[string]string {
	configOnce.Do(func() {
		fmt.Println("Loading config (once)...")
		config = map[string]string{
			"host": "localhost",
			"port": "8080",
		}
	})
	return config
}

// --- Atomic counter ---

type AtomicCounter struct {
	value int64
}

func (c *AtomicCounter) Add(delta int64) {
	atomic.AddInt64(&c.value, delta)
}

func (c *AtomicCounter) Value() int64 {
	return atomic.LoadInt64(&c.value)
}

func (c *AtomicCounter) Swap(new int64) int64 {
	return atomic.SwapInt64(&c.value, new)
}

// --- sync.Map for concurrent map ---

func main() {
	// Mutex counter
	var sc SafeCounter
	var wg sync.WaitGroup
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			sc.Increment()
		}()
	}
	wg.Wait()
	fmt.Println("SafeCounter:", sc.Value())

	// RWMutex cache
	cache := NewCache()
	cache.Set("key1", "value1")
	if v, ok := cache.Get("key1"); ok {
		fmt.Println("Cache get:", v)
	}

	// Once
	for i := 0; i < 3; i++ {
		go loadConfig()
	}

	// Atomic
	var ac AtomicCounter
	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			ac.Add(1)
		}()
	}
	wg.Wait()
	fmt.Println("AtomicCounter:", ac.Value())

	// sync.Map
	var sm sync.Map
	sm.Store("a", 1)
	sm.Store("b", 2)
	sm.Range(func(key, value interface{}) bool {
		fmt.Printf("sync.Map %v = %v\n", key, value)
		return true
	})

	time.Sleep(50 * time.Millisecond) // let goroutines finish
}

```
