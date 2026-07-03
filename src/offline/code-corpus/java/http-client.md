---
language: java
tags: [pattern, networking]
title: HTTP Client (java.net.http)
description: HttpClient, HttpRequest, HttpResponse, async send, BodyHandlers, and custom headers.
source: pattern
---

```java
import java.net.URI;
import java.net.http.*;
import java.net.http.HttpResponse.BodyHandlers;
import java.util.concurrent.*;

public class HttpClientDemo {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();

        // Synchronous GET
        HttpRequest getReq = HttpRequest.newBuilder()
                .uri(URI.create("https://httpbin.org/get"))
                .header("Accept", "application/json")
                .GET()
                .build();

        HttpResponse<String> syncResp = client.send(getReq, BodyHandlers.ofString());
        System.out.println("GET status: " + syncResp.statusCode());
        System.out.println("GET body (first 200 chars): " +
                           syncResp.body().substring(0, Math.min(200, syncResp.body().length())));

        // Asynchronous GET
        CompletableFuture<HttpResponse<String>> future = client.sendAsync(
                getReq, BodyHandlers.ofString());
        future.thenApply(HttpResponse::body)
              .thenAccept(body -> System.out.println("Async body length: " + body.length()))
              .join();

        // POST with JSON body
        String json = "{"name": "Alice", "email": "alice@example.com"}";
        HttpRequest postReq = HttpRequest.newBuilder()
                .uri(URI.create("https://httpbin.org/post"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json))
                .build();

        HttpResponse<String> postResp = client.send(postReq, BodyHandlers.ofString());
        System.out.println("POST status: " + postResp.statusCode());

        // Headers from response
        postResp.headers().map().forEach((k, v) ->
                System.out.println("  Header: " + k + " = " + v));
    }
}

```
