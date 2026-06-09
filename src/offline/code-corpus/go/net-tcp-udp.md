---
language: go
tags: [pattern, net, server]
title: Net (TCP/UDP)
description: net.Listen, net.Dial, TCP echo server/client, UDP server/client, and bufio for line-based I/O.
source: pattern
---

```go
package main

import (
	"bufio"
	"fmt"
	"log"
	"net"
	"os"
	"strings"
	"sync"
	"time"
)

// --- TCP Echo Server ---

func startTCPServer(addr string) (*net.TCPListener, error) {
	tcpAddr, err := net.ResolveTCPAddr("tcp", addr)
	if err != nil {
		return nil, err
	}
	listener, err := net.ListenTCP("tcp", tcpAddr)
	if err != nil {
		return nil, err
	}
	return listener, nil
}

func handleTCPConn(conn net.Conn) {
	defer conn.Close()
	log.Printf("TCP client connected: %s", conn.RemoteAddr())

	scanner := bufio.NewScanner(conn)
	for scanner.Scan() {
		text := scanner.Text()
		log.Printf("Received: %s", text)

		// Echo back
		response := strings.ToUpper(text)
		if _, err := fmt.Fprintln(conn, response); err != nil {
			log.Printf("Write error: %v", err)
			return
		}
	}
	if err := scanner.Err(); err != nil {
		log.Printf("Scanner error: %v", err)
	}
	log.Printf("TCP client disconnected: %s", conn.RemoteAddr())
}

func runTCPClient(addr, message string) (string, error) {
	conn, err := net.DialTimeout("tcp", addr, 5*time.Second)
	if err != nil {
		return "", fmt.Errorf("dial TCP: %w", err)
	}
	defer conn.Close()

	// Send message
	fmt.Fprintf(conn, "%s\n", message)

	// Read response
	response, err := bufio.NewReader(conn).ReadString('\n')
	if err != nil {
		return "", fmt.Errorf("read TCP: %w", err)
	}
	return strings.TrimSpace(response), nil
}

// --- UDP Server ---

func startUDPServer(addr string) (*net.UDPConn, error) {
	udpAddr, err := net.ResolveUDPAddr("udp", addr)
	if err != nil {
		return nil, err
	}
	conn, err := net.ListenUDP("udp", udpAddr)
	if err != nil {
		return nil, err
	}
	return conn, nil
}

func runUDPClient(addr, message string) (string, error) {
	conn, err := net.DialTimeout("udp", addr, 5*time.Second)
	if err != nil {
		return "", fmt.Errorf("dial UDP: %w", err)
	}
	defer conn.Close()

	// Send
	_, err = conn.Write([]byte(message))
	if err != nil {
		return "", fmt.Errorf("write UDP: %w", err)
	}

	// Read response
	buf := make([]byte, 1024)
	conn.SetReadDeadline(time.Now().Add(3 * time.Second))
	n, err := conn.Read(buf)
	if err != nil {
		return "", fmt.Errorf("read UDP: %w", err)
	}
	return string(buf[:n]), nil
}

func main() {
	// --- Start TCP server ---
	tcpListener, err := startTCPServer("127.0.0.1:0") // random port
	if err != nil {
		log.Fatal("TCP server:", err)
	}
	tcpAddr := tcpListener.Addr().String()
	fmt.Println("TCP server listening on", tcpAddr)

	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		for {
			conn, err := tcpListener.Accept()
			if err != nil {
				return
			}
			go handleTCPConn(conn)
		}
	}()

	// --- TCP client test ---
	response, err := runTCPClient(tcpAddr, "hello TCP")
	if err != nil {
		log.Fatal("TCP client:", err)
	}
	fmt.Println("TCP response:", response)

	// --- UDP test ---
	udpConn, err := startUDPServer("127.0.0.1:0")
	if err != nil {
		log.Fatal("UDP server:", err)
	}
	udpAddr := udpConn.LocalAddr().String()
	fmt.Println("UDP server listening on", udpAddr)

	wg.Add(1)
	go func() {
		defer wg.Done()
		buf := make([]byte, 1024)
		for {
			n, addr, err := udpConn.ReadFromUDP(buf)
			if err != nil {
				return
			}
			msg := strings.TrimSpace(string(buf[:n]))
			fmt.Printf("UDP received from %s: %s\n", addr, msg)
			udpConn.WriteToUDP([]byte("echo: "+msg), addr)
		}
	}()

	udpResponse, err := runUDPClient(udpAddr, "hello UDP")
	if err != nil {
		log.Fatal("UDP client:", err)
	}
	fmt.Println("UDP response:", udpResponse)

	tcpListener.Close()
	udpConn.Close()
	wg.Wait()

	// Prevent "unused" warnings
	_ = os.Stdout
	_ = strings.Contains
}

```
