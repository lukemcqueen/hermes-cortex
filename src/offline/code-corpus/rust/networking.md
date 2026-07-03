---
language: rust
tags: [net, pattern, async]
title: Networking
description: std::net::TcpListener/Stream, tokio::net, reqwest HTTP client, and URL parsing.
source: pattern
---

```rust
use std::io::{BufRead, BufReader, Write};
use std::net::{TcpListener, TcpStream};

// --- Synchronous TCP echo server ---
fn handle_client(mut stream: TcpStream) {
    let peer = stream.peer_addr().unwrap();
    println!("New connection from {peer}");

    let mut reader = BufReader::new(&stream);
    let mut line = String::new();
    if reader.read_line(&mut line).is_ok() && !line.is_empty() {
        let _ = write!(stream, "Echo: {line}");
    }
    println!("Closed connection from {peer}");
}

fn std_tcp_server() {
    let listener = TcpListener::bind("127.0.0.1:7878").unwrap();
    println!("TCP server listening on :7878");

    for stream in listener.incoming() {
        match stream {
            Ok(stream) => { handle_client(stream); }
            Err(e) => eprintln!("Connection failed: {e}"),
        }
    }
}

// --- Tokio TCP (async) ---
async fn tokio_tcp_server() {
    use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
    use tokio::net::TcpListener;

    let listener = TcpListener::bind("127.0.0.1:7879").await.unwrap();
    println!("Tokio TCP server on :7879");

    loop {
        let (mut stream, addr) = listener.accept().await.unwrap();
        println!("Tokio accepted: {addr}");

        tokio::spawn(async move {
            let mut reader = BufReader::new(&mut stream);
            let mut line = String::new();
            if reader.read_line(&mut line).await.is_ok() {
                let _ = stream.write_all(format!("Echo: {line}").as_bytes()).await;
            }
        });
    }
}

// --- Reqwest HTTP client ---
async fn http_client_demo() -> Result<(), reqwest::Error> {
    let client = reqwest::Client::new();

    // GET
    let resp = client.get("https://httpbin.org/get")
        .query(&[("name", "rust")])
        .send()
        .await?;
    println!("GET status: {}", resp.status());

    // POST JSON
    let body = serde_json::json!({"key": "value"});
    let resp = client.post("https://httpbin.org/post")
        .json(&body)
        .send()
        .await?;
    println!("POST status: {}", resp.status());

    Ok(())
}

// --- URL parsing ---
fn url_parse_demo() {
    let url = url::Url::parse("https://user:pass@example.com:8080/path?q=rust#section").unwrap();
    println!("Scheme: {}", url.scheme());
    println!("Host: {:?}", url.host());
    println!("Port: {:?}", url.port());
    println!("Path: {}", url.path());
    println!("Query: {:?}", url.query());
}

```
