---
language: kotlin
tags: [kotlin, Ktor, embeddedServer, routing, get, post, content-negotiation, client]
title: Kotlin Ktor HTTP
description: Shows a basic Ktor HTTP server with routing, content negotiation (JSON), and a Ktor client making requests.
source: pattern
---

```kotlin
import io.ktor.server.application.*
import io.ktor.server.engine.*
import io.ktor.server.netty.*
import io.ktor.server.routing.*
import io.ktor.server.response.*
import io.ktor.server.request.*
import io.ktor.serialization.kotlinx.json.*
import io.ktor.client.*
import io.ktor.client.request.*
import io.ktor.client.statement.*
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

@Serializable
data class Message(val text: String, val author: String = "anonymous")

fun main() {
    val json = Json { ignoreUnknownKeys = true }

    // Server
    val server = embeddedServer(Netty, port = 8080) {
        install(io.ktor.server.plugins.contentnegotiation.ContentNegotiation) {
            json(json)
        }

        routing {
            get("/") {
                call.respondText("Hello, Ktor!")
            }

            get("/api/message") {
                call.respond(Message("Hello!", "Ktor"))
            }

            post("/api/message") {
                val msg = call.receive<Message>()
                println("Received: $msg")
                call.respond(mapOf("status" to "ok"))
            }
        }
    }

    // Client (would normally be separate)
    runBlocking {
        val client = HttpClient()
        val response: HttpResponse = client.get("http://localhost:8080/")
        println(response.bodyAsText())
        client.close()
    }

    server.start(wait = true)
}

// Note: requires build.gradle.kts dependencies:
//   implementation("io.ktor:ktor-server-netty")
//   implementation("io.ktor:ktor-server-content-negotiation")
//   implementation("io.ktor:ktor-serialization-kotlinx-json")
//   implementation("io.ktor:ktor-client-core")
//   implementation("io.ktor:ktor-client-cio")

```
