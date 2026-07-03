---
language: kotlin
tags: [kotlin, class, data-class, sealed-class, object, companion, open, abstract]
title: Classes & OOP
description: Covers Kotlin OOP: class, data class, sealed class, object declarations, companion objects, open/final, and abstract classes.
source: pattern
---

```kotlin
import kotlin.random.Random

// Data class — automatic equals/hashCode/toString/copy
data class User(val id: Int, val name: String, val email: String? = null)

// Open class (extendable)
open class Animal(val name: String) {
    open fun speak(): String = "$name makes a sound"
}

class Dog(name: String) : Animal(name) {
    override fun speak(): String = "$name barks"
}

// Abstract class
abstract class Shape {
    abstract fun area(): Double
}

class Circle(val radius: Double) : Shape() {
    override fun area(): Double = Math.PI * radius * radius
}

// Sealed class — restricted hierarchy
sealed class NetworkResult {
    data class Success(val data: String) : NetworkResult()
    data class Error(val message: String) : NetworkResult()
    object Loading : NetworkResult()
}

// Object — singleton
object Config {
    val baseUrl = "https://api.example.com"
    fun timeout(): Long = 30_000
}

// Companion object — static-like members
class Database {
    companion object {
        private var instance: Database? = null
        fun getInstance(): Database =
            instance ?: Database().also { instance = it }
    }
}

fun main() {
    val user = User(1, "Alice")
    val dog = Dog("Rex")
    println(dog.speak())
}

```
