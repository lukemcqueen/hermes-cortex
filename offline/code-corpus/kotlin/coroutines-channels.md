---
language: kotlin
tags: [kotlin, Channel, produce, consume, BroadcastChannel, ticker, select]
title: Kotlinx Coroutines Channels
description: Shows coroutine channels: Channel basics, produce/consume, BroadcastChannel (SharedFlow), ticker, and select expression.
source: pattern
---

```kotlin
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.*

fun main() = runBlocking {
    // Basic Channel (rendezvous by default)
    val channel = Channel<Int>(capacity = 2)

    launch {
        for (i in 1..5) {
            println("Sending $i")
            channel.send(i)
        }
        channel.close()
    }

    launch {
        for (value in channel) {
            println("Received $value")
            delay(50)
        }
    }

    // Produce / Consume
    val producer = produce {
        for (i in 1..3) {
            send(i * 10)
        }
    }
    producer.consumeEach { println("produced: $it") }

    // BroadcastChannel (deprecated in favor of SharedFlow)
    val shared = MutableSharedFlow<Int>(replay = 1)
    launch {
        repeat(5) { shared.emit(it) }
    }
    delay(100)

    // Ticker channel
    val ticker = ticker(100, initialDelayMillis = 0)
    launch {
        repeat(3) {
            ticker.receive()
            println("tick $it")
        }
        ticker.cancel()
    }

    // select expression
    val chan1 = Channel<String>(10)
    val chan2 = Channel<String>(10)

    launch {
        select<Unit> {
            chan1.onReceive { println("chan1: $it") }
            chan2.onReceive { println("chan2: $it") }
        }
    }

    chan1.send("from 1")
    delay(50)
    chan2.send("from 2")

    delay(200)
}

```
