---
language: go
tags: [pattern, db, sql]
title: SQL Database
description: database/sql with sql.Open, Query, Exec, prepared statements, rows.Scan, and transactions.
source: pattern
---

```go
package main

import (
	"database/sql"
	"fmt"
	"log"
	"time"

	_ "github.com/lib/pq" // PostgreSQL driver
	// _ "github.com/mattn/go-sqlite3" // or SQLite driver
)

type User struct {
	ID        int
	Name      string
	Email     string
	CreatedAt time.Time
}

// --- Setup ---

func initDB(dsn string) (*sql.DB, error) {
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return nil, fmt.Errorf("opening DB: %w", err)
	}
	// Connection pool settings
	db.SetMaxOpenConns(25)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(5 * time.Minute)

	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("pinging DB: %w", err)
	}
	return db, nil
}

func createTables(db *sql.DB) error {
	query := `
	CREATE TABLE IF NOT EXISTS users (
		id   SERIAL PRIMARY KEY,
		name TEXT NOT NULL,
		email TEXT UNIQUE NOT NULL,
		created_at TIMESTAMPTZ DEFAULT NOW()
	)`
	_, err := db.Exec(query)
	return err
}

// --- CRUD ---

func insertUser(db *sql.DB, name, email string) (int, error) {
	query := `INSERT INTO users (name, email) VALUES ($1, $2) RETURNING id`
	var id int
	err := db.QueryRow(query, name, email).Scan(&id)
	if err != nil {
		return 0, fmt.Errorf("inserting user: %w", err)
	}
	return id, nil
}

func getUser(db *sql.DB, id int) (*User, error) {
	query := `SELECT id, name, email, created_at FROM users WHERE id = $1`
	u := &User{}
	err := db.QueryRow(query, id).Scan(&u.ID, &u.Name, &u.Email, &u.CreatedAt)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("user %d not found", id)
		}
		return nil, fmt.Errorf("querying user: %w", err)
	}
	return u, nil
}

func listUsers(db *sql.DB) ([]User, error) {
	query := `SELECT id, name, email, created_at FROM users ORDER BY created_at DESC`
	rows, err := db.Query(query)
	if err != nil {
		return nil, fmt.Errorf("listing users: %w", err)
	}
	defer rows.Close()

	var users []User
	for rows.Next() {
		var u User
		if err := rows.Scan(&u.ID, &u.Name, &u.Email, &u.CreatedAt); err != nil {
			return nil, fmt.Errorf("scanning row: %w", err)
		}
		users = append(users, u)
	}
	return users, rows.Err()
}

func updateUserEmail(db *sql.DB, id int, email string) error {
	query := `UPDATE users SET email = $1 WHERE id = $2`
	result, err := db.Exec(query, email, id)
	if err != nil {
		return fmt.Errorf("updating user: %w", err)
	}
	n, _ := result.RowsAffected()
	if n == 0 {
		return fmt.Errorf("user %d not found", id)
	}
	return nil
}

func deleteUser(db *sql.DB, id int) error {
	query := `DELETE FROM users WHERE id = $1`
	result, err := db.Exec(query, id)
	if err != nil {
		return fmt.Errorf("deleting user: %w", err)
	}
	n, _ := result.RowsAffected()
	if n == 0 {
		return fmt.Errorf("user %d not found", id)
	}
	return nil
}

// --- Transaction ---

func createUsersTx(db *sql.DB, users []User) error {
	tx, err := db.Begin()
	if err != nil {
		return fmt.Errorf("beginning tx: %w", err)
	}
	defer tx.Rollback() // no-op if committed

	stmt, err := tx.Prepare(`INSERT INTO users (name, email) VALUES ($1, $2)`)
	if err != nil {
		return fmt.Errorf("preparing stmt: %w", err)
	}
	defer stmt.Close()

	for _, u := range users {
		if _, err := stmt.Exec(u.Name, u.Email); err != nil {
			return fmt.Errorf("inserting in tx: %w", err)
		}
	}
	return tx.Commit()
}

func main() {
	// Example usage (requires a running Postgres/SQLite instance)
	db, err := initDB("host=localhost port=5432 user=app dbname=app sslmode=disable")
	if err != nil {
		log.Fatal(err)
	}
	defer db.Close()

	if err := createTables(db); err != nil {
		log.Fatal(err)
	}

	id, _ := insertUser(db, "Alice", "alice@example.com")
	u, _ := getUser(db, id)
	fmt.Printf("Created: %+v\n", u)
}

```
