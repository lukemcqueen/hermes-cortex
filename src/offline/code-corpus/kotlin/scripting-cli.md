---
language: kotlin
tags: [kotlin, script, kts, kotlin-main-kts, CLI, args]
title: Kotlin Scripting & CLI
description: Shows Kotlin scripting (.kts), kotlin-main-kts dependency resolution, and command-line argument parsing patterns.
source: pattern
---

```kotlin
// 1. Basic .kts script — run with: kotlin myscript.kts
// File: hello.kts
val name = args.firstOrNull() ?: "world"
println("Hello, $name!")

// 2. kotlin-main-kts with dependencies
// File: fetch.kts
//!/usr/bin/env kotlin
@file:DependsOn("com.squareup.okhttp3:okhttp:4.12.0")
@file:DependsOn("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.2")

import okhttp3.OkHttpClient
import okhttp3.Request

val client = OkHttpClient()
val request = Request.Builder()
    .url(args.firstOrNull() ?: "https://httpbin.org/get")
    .build()

client.newCall(request).execute().use { response ->
    println(response.body?.string()?.take(200))
}

// 3. Simple CLI using Kotlin main
// File: CliApp.kt
class CliApp {
    companion object {
        @JvmStatic
        fun main(args: Array<String>) {
            val options = mutableMapOf<String, String>()
            var positional = mutableListOf<String>()

            var i = 0
            while (i < args.size) {
                when {
                    args[i].startsWith("--") -> {
                        val key = args[i].removePrefix("--")
                        val value = args.getOrElse(i + 1) { "true" }
                        options[key] = value
                        i += if (value != "true") 2 else 1
                    }
                    else -> {
                        positional.add(args[i])
                        i++
                    }
                }
            }

            println("Options: $options")
            println("Positional: $positional")
        }
    }
}

// 4. Run with: kotlin -cp ... CliAppKt --name Alice --verbose file.txt

```
