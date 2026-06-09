---
language: kotlin
tags: [kotlin, coroutine, launch, async, await, runBlocking, Flow, collect, StateFlow]
title: Coroutines & Flow
description: Covers Kotlin coroutines: launch, async/await, runBlocking, withContext, Flow builders, collect, and StateFlow for reactive state.
source: pattern
---

```kotlin
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*

// Basic coroutine
suspend fun fetchUser(id: Int): String {
    delay(100) // simulate network
    return "User $id"
}

fun main() = runBlocking {
    // Launch (fire-and-forget)
    val job = launch {
        val user = fetchUser(1)
        println(user)
    }
    job.join()

    // Async/await (return a value)
    val deferred = async { fetchUser(2) }
    println(deferred.await())

    // withContext — switch dispatcher
    val result = withContext(Dispatchers.IO) {
        fetchUser(3)
    }

    // Flow — cold stream
    val numberFlow = flow {
        for (i in 1..3) {
            delay(100)
            emit(i)
        }
    }

    numberFlow
        .map { it * 2 }
        .filter { it > 2 }
        .collect { println(it) }

    // StateFlow — observable state
    val state = MutableStateFlow("initial")
    val job2 = launch {
        state.collect { println("State: $it") }
    }
    state.value = "updated"
    delay(50)
    job2.cancel()
}

```
