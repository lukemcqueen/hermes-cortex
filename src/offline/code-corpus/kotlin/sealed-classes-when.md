---
language: kotlin
tags: [kotlin, sealed-class, sealed-interface, when, exhaustive, Result]
title: Sealed Classes & When
description: Covers Kotlin sealed classes/interfaces, exhaustive when expressions, and the Result type for functional error handling.
source: pattern
---

```kotlin
// Sealed interface (Kotlin 1.5+)
sealed interface ApiResponse<out T> {
    data class Success<T>(val data: T) : ApiResponse<T>
    data class Error(val message: String, val code: Int) : ApiResponse<Nothing>
    object Loading : ApiResponse<Nothing>
}

// Exhaustive when (compiler-enforced)
fun <T> handleResponse(response: ApiResponse<T>): String = when (response) {
    is ApiResponse.Success -> "Data: ${response.data}"
    is ApiResponse.Error -> "Error ${response.code}: ${response.message}"
    ApiResponse.Loading -> "Loading..."
    // No 'else' needed — sealed hierarchy is exhaustive
}

// Sealed class (classic form)
sealed class Either<out L, out R> {
    data class Left<L>(val value: L) : Either<L, Nothing>()
    data class Right<R>(val value: R) : Either<Nothing, R>()
}

fun parse(input: String): Either<Exception, Int> =
    try {
        Either.Right(input.toInt())
    } catch (e: NumberFormatException) {
        Either.Left(e)
    }

// Kotlin Result (built-in)
fun riskyOperation(): Result<String> = runCatching {
    if (Random.nextBoolean()) "success" else throw RuntimeException("fail")
}

fun main() {
    val res = riskyOperation()
    res
        .onSuccess { println("OK: $it") }
        .onFailure { println("FAIL: ${it.message}") }

    println(handleResponse(ApiResponse.Loading))

    when (parse("42")) {
        is Either.Left -> println("Parse error")
        is Either.Right -> println("Got number")
    }
}

```
