---
language: kotlin
tags: [kotlin, DSL, type-safe-builder, DslMarker, receiver, builder-pattern]
title: DSL Builders
description: Shows Kotlin type-safe DSL builders: receiver-based lambda, @DslMarker to restrict implicit receivers, and a practical HTML-like DSL example.
source: pattern
---

```kotlin
import kotlinx.html.*
import kotlinx.html.stream.createHTML

// Mark DSL scope to prevent outer receiver leakage
@DslMarker
annotation class HtmlDsl

// Node abstraction
@HtmlDsl
abstract class Node {
    val children = mutableListOf<Node>()
}

@HtmlDsl
class Text(val content: String) : Node()

@HtmlDsl
class Div : Node() {
    fun text(content: String) {
        children.add(Text(content))
    }
}

@HtmlDsl
class Html : Node() {
    fun div(block: Div.() -> Unit) {
        val d = Div()
        d.block()
        children.add(d)
    }

    fun text(content: String) {
        children.add(Text(content))
    }
}

// Builder entry point
fun html(block: Html.() -> Unit): Html =
    Html().apply(block)

// Render
fun Node.render(): String = when (this) {
    is Text -> content
    is Div -> "<div>${children.joinToString("") { it.render() }}</div>"
    is Html -> children.joinToString("") { it.render() }
    else -> ""
}

fun main() {
    val doc = html {
        div {
            text("Hello")
            div {
                text("Nested")
            }
        }
        text("World")
    }
    println(doc.render())
    // <div>Hello<div>Nested</div></div>World
}

// Alternative example using kotlinx.html library
fun generateHtml(): String = createHTML().html {
    body {
        div {
            +"Hello from kotlinx.html"
        }
    }
}

```
