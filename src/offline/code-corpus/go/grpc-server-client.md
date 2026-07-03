---
language: go
tags: [go, grpc, protobuf, networking]
title: gRPC Server and Client with Protobuf
description: gRPC helloworld example with protoc commands, reflection, and TLS
source: pattern
---

# gRPC Server and Client (Go)

End-to-end gRPC example with protocol buffers, server reflection, and TLS.

## Project Setup

```shell
mkdir -p grpc-helloworld
cd grpc-helloworld
go mod init github.com/user/grpc-helloworld
```

Install tools:

```shell
# protoc compiler
brew install protobuf                 # macOS
apt install protobuf-compiler         # Linux

# Go plugins for protoc
go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest

# grpcurl for reflection-based debugging
go install github.com/fullstorydev/grpcurl/cmd/grpcurl@latest

# Verify
protoc --version
protoc-gen-go --version
protoc-gen-go-grpc --version
```

## Step 1: Define the Protobuf Service

```protobuf
// proto/helloworld/v1/helloworld.proto
syntax = "proto3";

package helloworld.v1;

option go_package = "github.com/user/grpc-helloworld/gen/helloworld/v1;helloworldv1";

// The greeting service definition.
service Greeter {
  // Sends a greeting
  rpc SayHello (HelloRequest) returns (HelloReply);
  // Server-streaming: multiple replies
  rpc SayHelloStream (HelloRequest) returns (stream HelloReply);
}

// The request message containing the user's name.
message HelloRequest {
  string name = 1;
}

// The response message containing the greetings.
message HelloReply {
  string message = 1;
}
```

## Step 2: Generate Go Code

```shell
# From project root
protoc \
  --go_out=. \
  --go_opt=paths=source_relative \
  --go-grpc_out=. \
  --go-grpc_opt=paths=source_relative \
  proto/helloworld/v1/helloworld.proto

# Generated files:
# gen/helloworld/v1/helloworld.pb.go          # message types
# gen/helloworld/v1/helloworld_grpc.pb.go     # client + server stubs
```

## Step 3: Server Implementation

```go
// cmd/server/main.go
package main

import (
    "context"
    "fmt"
    "log"
    "net"
    "time"

    "google.golang.org/grpc"
    "google.golang.org/grpc/reflection"

    helloworldv1 "github.com/user/grpc-helloworld/gen/helloworld/v1"
)

type greeterServer struct {
    helloworldv1.UnimplementedGreeterServer
}

func (s *greeterServer) SayHello(
    ctx context.Context,
    req *helloworldv1.HelloRequest,
) (*helloworldv1.HelloReply, error) {
    log.Printf("SayHello called with name=%q", req.GetName())
    msg := fmt.Sprintf("Hello, %s!", req.GetName())
    return &helloworldv1.HelloReply{Message: msg}, nil
}

func (s *greeterServer) SayHelloStream(
    req *helloworldv1.HelloRequest,
    stream helloworldv1.Greeter_SayHelloStreamServer,
) error {
    log.Printf("SayHelloStream called with name=%q", req.GetName())
    greetings := []string{
        fmt.Sprintf("Hello, %s!", req.GetName()),
        fmt.Sprintf("How are you, %s?", req.GetName()),
        fmt.Sprintf("Goodbye, %s!", req.GetName()),
    }
    for _, g := range greetings {
        if err := stream.Send(&helloworldv1.HelloReply{Message: g}); err != nil {
            return err
        }
        time.Sleep(500 * time.Millisecond)
    }
    return nil
}

func main() {
    lis, err := net.Listen("tcp", ":50051")
    if err != nil {
        log.Fatalf("failed to listen: %v", err)
    }

    srv := grpc.NewServer()

    helloworldv1.RegisterGreeterServer(srv, &greeterServer{})

    // Enable reflection — allows grpcurl and other tools to discover services
    reflection.Register(srv)

    log.Printf("gRPC server listening on %s", lis.Addr())
    if err := srv.Serve(lis); err != nil {
        log.Fatalf("failed to serve: %v", err)
    }
}
```

## Step 4: Client Implementation

```go
// cmd/client/main.go
package main

import (
    "context"
    "flag"
    "io"
    "log"
    "time"

    "google.golang.org/grpc"
    "google.golang.org/grpc/credentials/insecure"

    helloworldv1 "github.com/user/grpc-helloworld/gen/helloworld/v1"
)

func main() {
    addr := flag.String("addr", "localhost:50051", "server address")
    name := flag.String("name", "World", "greeting name")
    stream := flag.Bool("stream", false, "use streaming RPC")
    flag.Parse()

    conn, err := grpc.NewClient(
        *addr,
        grpc.WithTransportCredentials(insecure.NewCredentials()),
    )
    if err != nil {
        log.Fatalf("failed to dial: %v", err)
    }
    defer conn.Close()

    client := helloworldv1.NewGreeterClient(conn)
    ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
    defer cancel()

    if *stream {
        handleStream(ctx, client, *name)
    } else {
        handleUnary(ctx, client, *name)
    }
}

func handleUnary(ctx context.Context, client helloworldv1.GreeterClient, name string) {
    resp, err := client.SayHello(ctx, &helloworldv1.HelloRequest{Name: name})
    if err != nil {
        log.Fatalf("SayHello failed: %v", err)
    }
    log.Printf("Response: %s", resp.GetMessage())
}

func handleStream(ctx context.Context, client helloworldv1.GreeterClient, name string) {
    stream, err := client.SayHelloStream(ctx, &helloworldv1.HelloRequest{Name: name})
    if err != nil {
        log.Fatalf("SayHelloStream failed: %v", err)
    }
    for {
        resp, err := stream.Recv()
        if err == io.EOF {
            break
        }
        if err != nil {
            log.Fatalf("stream recv error: %v", err)
        }
        log.Printf("Stream: %s", resp.GetMessage())
    }
}
```

## Step 5: TLS (Mutual TLS Example)

Generate self-signed certs for testing:

```shell
# CA key + cert
openssl genrsa -out ca.key 4096
openssl req -x509 -new -nodes -key ca.key -sha256 -days 365 \
  -subj "/CN=Test CA" -out ca.crt

# Server key + CSR
openssl genrsa -out server.key 2048
openssl req -new -key server.key -subj "/CN=localhost" -out server.csr

# Server cert signed by CA
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt -days 365 -sha256 -extfile <(echo "subjectAltName=DNS:localhost,IP:127.0.0.1")

# Client key + cert
openssl genrsa -out client.key 2048
openssl req -new -key client.key -subj "/CN=client" -out client.csr
openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out client.crt -days 365 -sha256
```

TLS server:

```go
// cmd/server-tls/main.go (excerpt)
import (
    "google.golang.org/grpc/credentials"
)

func main() {
    creds, err := credentials.NewServerTLSFromFile("server.crt", "server.key")
    if err != nil {
        log.Fatalf("failed to load TLS: %v", err)
    }

    // mTLS — require client certs
    tlsConfig := &tls.Config{
        Certificates: []tls.Certificate{serverCert},
        ClientAuth:   tls.RequireAndVerifyClientCert,
        ClientCAs:    caCertPool,
    }
    creds := credentials.NewTLS(tlsConfig)

    srv := grpc.NewServer(grpc.Creds(creds))
    // ... register services as before
}
```

TLS client:

```go
// cmd/client-tls/main.go (excerpt)
import (
    "google.golang.org/grpc/credentials"
)

func main() {
    creds, err := credentials.NewClientTLSFromFile("ca.crt", "localhost")
    if err != nil {
        log.Fatalf("failed to load CA: %v", err)
    }

    // mTLS — present client cert
    cert, err := tls.LoadX509KeyPair("client.crt", "client.key")
    tlsConfig := &tls.Config{
        Certificates: []tls.Certificate{cert},
        RootCAs:      caCertPool,
        ServerName:   "localhost",
    }
    creds := credentials.NewTLS(tlsConfig)

    conn, err := grpc.NewClient(
        "localhost:50051",
        grpc.WithTransportCredentials(creds),
    )
    // ...
}
```

## Reflection and Debugging with grpcurl

```shell
# List services (requires reflection enabled on the server)
grpcurl -plaintext localhost:50051 list

# List methods on a service
grpcurl -plaintext localhost:50051 list helloworld.v1.Greeter

# Describe a message type
grpcurl -plaintext localhost:50051 describe helloworld.v1.HelloRequest

# Call a unary RPC
grpcurl -plaintext -d '{"name": "Alice"}' \
  localhost:50051 helloworld.v1.Greeter/SayHello

# Call with TLS
grpcurl -cacert ca.crt -cert client.crt -key client.key \
  -d '{"name": "Bob"}' \
  localhost:50051 helloworld.v1.Greeter/SayHello

# Stream response (one-shot, prints all messages)
grpcurl -plaintext -d '{"name": "Stream"}' \
  localhost:50051 helloworld.v1.Greeter/SayHelloStream
```

## Interceptors (Server-Side Logging)

```go
// pkg/interceptors/logging.go
import (
    "log"
    "time"

    "google.golang.org/grpc"
    "google.golang.org/grpc/status"
)

func UnaryLoggingInterceptor(
    ctx context.Context,
    req interface{},
    info *grpc.UnaryServerInfo,
    handler grpc.UnaryHandler,
) (interface{}, error) {
    start := time.Now()
    resp, err := handler(ctx, req)
    dur := time.Since(start)
    st := status.Convert(err)
    log.Printf("[gRPC] %s duration=%s code=%s", info.FullMethod, dur, st.Code())
    return resp, err
}

// Register on the server:
// srv := grpc.NewServer(grpc.UnaryInterceptor(UnaryLoggingInterceptor))
```

## Module Dependencies

```shell
# Install dependencies
go get google.golang.org/grpc
go get google.golang.org/protobuf

# tidying
go mod tidy
```

## Running

```shell
# Terminal 1: server
go run cmd/server/main.go

# Terminal 2: unary client
go run cmd/client/main.go -name Alice

# Terminal 2: streaming client
go run cmd/client/main.go -name Bob -stream
```

### Directory Structure

```
grpc-helloworld/
├── proto/
│   └── helloworld/
│       └── v1/
│           └── helloworld.proto
├── gen/
│   └── helloworld/
│       └── v1/
│           ├── helloworld.pb.go
│           └── helloworld_grpc.pb.go
├── cmd/
│   ├── server/main.go
│   └── client/main.go
├── pkg/
│   └── interceptors/logging.go
├── go.mod
└── go.sum
```