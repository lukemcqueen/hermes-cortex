---
language: kotlin
tags: [kotlin, nullable, elvis, safe-call, let, also, apply, run, with]
title: Null Safety & Elvis
description: Shows Kotlin null safety: ? nullable types, ?. safe calls, !! not-null assertion, elvis ?:, and scope functions let/also/apply/run/with.
source: pattern
---

```kotlin
data class Address(val street: String?, val city: String)
data class Person(val name: String, val address: Address?)

// Safe call operator
fun getCity(person: Person?): String? = person?.address?.city

// Elvis operator
fun getCityOrDefault(person: Person?): String =
    person?.address?.city ?: "Unknown"

// Not-null assertion (only when you're sure)
fun getCityForce(person: Person?): String =
    person!!.address!!.city

// let — execute if non-null
fun printCity(person: Person?) {
    person?.address?.city?.let { city ->
        println("City: $city")
    }
}

// also — side-effect chaining
val user = Person("Alice", Address("123 Main", "NYC")).also {
    println("Created user: ${it.name}")
}

// apply — configure object
val configured = Person("Bob", null).apply {
    // 'this' is the Person
}

// run — scoped result
val upper = person?.run {
    name.uppercase()
}

// with — non-extension scope
with(person) {
    println("Name: ${this?.name}")
}

fun main() {
    println(getCityOrDefault(Person("Alice", Address(null, "NYC"))))
    // Unknown
}

```
