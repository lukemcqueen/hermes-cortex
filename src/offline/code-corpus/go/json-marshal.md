---
language: go
tags: [pattern, io, serialization]
title: JSON Marshal/Unmarshal
description: json.Marshal, json.Unmarshal, struct tags, custom MarshalJSON/UnmarshalJSON, and streaming with Encoder/Decoder.
source: pattern
---

```go
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"
)

// --- Struct with tags ---

type Person struct {
	Name    string    `json:"name"`
	Email   string    `json:"email,omitempty"`
	Age     int       `json:"age"`
	Created time.Time `json:"created"`
	// Unexported field — not marshalled
	internalID int `json:"-"`
}

// --- Custom JSON marshalling ---

type Password string

func (p Password) MarshalJSON() ([]byte, error) {
	return json.Marshal("****")
}

func (p *Password) UnmarshalJSON(data []byte) error {
	var s string
	if err := json.Unmarshal(data, &s); err != nil {
		return err
	}
	if len(s) < 8 {
		return fmt.Errorf("password too short")
	}
	*p = Password(s)
	return nil
}

type User struct {
	Username string   `json:"username"`
	Password Password `json:"password"`
}

func main() {
	// Marshal
	p := Person{
		Name:  "Alice",
		Email: "alice@example.com",
		Age:   30,
	}
	p.internalID = 42

	data, err := json.Marshal(p)
	if err != nil {
		panic(err)
	}
	fmt.Println("Marshal:", string(data))

	data, _ = json.MarshalIndent(p, "", "  ")
	fmt.Println("Pretty:", string(data))

	// Unmarshal
	input := `{"name":"Bob","email":"bob@test.com","age":25}`
	var p2 Person
	if err := json.Unmarshal([]byte(input), &p2); err != nil {
		panic(err)
	}
	fmt.Printf("Unmarshal: %+v\n", p2)

	// Custom marshalling
	u := User{Username: "alice", Password: "supersecret123"}
	data, _ = json.Marshal(u)
	fmt.Println("Custom marshal:", string(data))

	var u2 User
	json.Unmarshal([]byte(`{"username":"bob","password":"mypassword123"}`), &u2)
	fmt.Printf("Custom unmarshal: %+v\n", u2)

	// Streaming with Decoder
	reader := strings.NewReader(`{"name":"Eve","age":28}`)
	var p3 Person
	if err := json.NewDecoder(reader).Decode(&p3); err != nil {
		panic(err)
	}
	fmt.Printf("Stream decoded: %+v\n", p3)

	// Streaming with Encoder
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	enc.Encode(map[string]interface{}{"status": "ok", "count": 42})
}

```
