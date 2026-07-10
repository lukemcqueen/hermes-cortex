---
language: go
tags: [pattern, crypto, security]
title: Crypto
description: crypto/sha256, crypto/rand, crypto/aes, bcrypt password hashing, and HMAC signing.
source: pattern
---

```go
package main

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"io"

	// In a real project: go get golang.org/x/crypto/bcrypt
	// "golang.org/x/crypto/bcrypt"
)

// --- SHA-256 hashing ---

func hashSHA256(data string) string {
	h := sha256.Sum256([]byte(data))
	return hex.EncodeToString(h[:])
}

func hashSHA256Reader(r io.Reader) (string, error) {
	h := sha256.New()
	if _, err := io.Copy(h, r); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

// --- HMAC ---

func generateHMAC(key, data []byte) string {
	mac := hmac.New(sha256.New, key)
	mac.Write(data)
	return hex.EncodeToString(mac.Sum(nil))
}

func verifyHMAC(key, data []byte, expectedMAC string) bool {
	computed := generateHMAC(key, data)
	return hmac.Equal([]byte(computed), []byte(expectedMAC))
}

// --- AES-GCM encryption ---

func generateAESKey() ([]byte, error) {
	key := make([]byte, 32) // AES-256
	if _, err := rand.Read(key); err != nil {
		return nil, fmt.Errorf("generating key: %w", err)
	}
	return key, nil
}

func encryptAESGCM(key, plaintext []byte) ([]byte, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, fmt.Errorf("creating cipher: %w", err)
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("creating GCM: %w", err)
	}

	nonce := make([]byte, gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return nil, fmt.Errorf("generating nonce: %w", err)
	}

	// Seal appends encrypted data to nonce
	ciphertext := gcm.Seal(nonce, nonce, plaintext, nil)
	return ciphertext, nil
}

func decryptAESGCM(key, ciphertext []byte) ([]byte, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, fmt.Errorf("creating cipher: %w", err)
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("creating GCM: %w", err)
	}

	nonceSize := gcm.NonceSize()
	if len(ciphertext) < nonceSize {
		return nil, fmt.Errorf("ciphertext too short")
	}

	nonce, ciphertext := ciphertext[:nonceSize], ciphertext[nonceSize:]
	return gcm.Open(nil, nonce, ciphertext, nil)
}

// --- Secure random ---

func generateRandomString(length int) (string, error) {
	bytes := make([]byte, length)
	if _, err := rand.Read(bytes); err != nil {
		return "", err
	}
	return base64.URLEncoding.EncodeToString(bytes), nil
}

func generateRandomHex(length int) (string, error) {
	bytes := make([]byte, length)
	if _, err := rand.Read(bytes); err != nil {
		return "", err
	}
	return hex.EncodeToString(bytes), nil
}

// --- BCrypt (commented example) ---

/*
func hashPassword(password string) (string, error) {
	bytes, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	return string(bytes), err
}

func checkPassword(password, hash string) bool {
	err := bcrypt.CompareHashAndPassword([]byte(hash), []byte(password))
	return err == nil
}
*/

func main() {
	// SHA-256
	fmt.Println("SHA-256:", hashSHA256("hello world"))

	// HMAC
	key := []byte("secret-key")
	data := []byte("message-to-sign")
	sig := generateHMAC(key, data)
	fmt.Println("HMAC:", sig)
	fmt.Println("Verify:", verifyHMAC(key, data, sig))

	// AES-GCM
	encKey, _ := generateAESKey()
	encrypted, _ := encryptAESGCM(encKey, []byte("sensitive data"))
	decrypted, _ := decryptAESGCM(encKey, encrypted)
	fmt.Println("AES decrypted:", string(decrypted))

	// Secure random
	token, _ := generateRandomString(16)
	fmt.Println("Random token:", token)

	hexToken, _ := generateRandomHex(8)
	fmt.Println("Hex token:", hexToken)

	_ = hashSHA256Reader
}

```
