"""Go snippets — 20 entries covering idiomatic Go patterns and stdlib packages."""

SNIPPETS = [
    # ═══════════════════════════════════════════════════════════
    # 1. STRUCTS, METHODS & INTERFACES
    # ═══════════════════════════════════════════════════════════
    ("go/structs-interfaces.md", "go", ["pattern", "oop"],
     "Structs, Methods & Interfaces",
     "Go structs with value/pointer receivers, interface satisfaction, and type assertions.",
     "pattern",
     """package main

import (
	"fmt"
	"math"
)

// --- Interfaces ---

type Shape interface {
	Area() float64
	Perimeter() float64
}

type Describer interface {
	Description() string
}

// --- Structs ---

type Circle struct {
	Radius float64
}

// Value receiver — operates on a copy.
func (c Circle) Area() float64 {
	return math.Pi * c.Radius * c.Radius
}

func (c Circle) Perimeter() float64 {
	return 2 * math.Pi * c.Radius
}

// Pointer receiver — can modify the receiver.
func (c *Circle) Scale(factor float64) {
	c.Radius *= factor
}

func (c Circle) Description() string {
	return fmt.Sprintf("Circle with radius %.2f", c.Radius)
}

type Rectangle struct {
	Width, Height float64
}

func (r Rectangle) Area() float64 {
	return r.Width * r.Height
}

func (r Rectangle) Perimeter() float64 {
	return 2 * (r.Width + r.Height)
}

func (r Rectangle) Description() string {
	return fmt.Sprintf("Rectangle %.2f x %.2f", r.Width, r.Height)
}

// --- Interface satisfaction & type assertion ---

func printShapeInfo(s Shape) {
	// Type assertion to access concrete type
	if desc, ok := s.(Describer); ok {
		fmt.Println(desc.Description())
	}
	fmt.Printf("  Area: %.2f, Perimeter: %.2f\\n", s.Area(), s.Perimeter())
}

func main() {
	circle := Circle{Radius: 5}
	rect := Rectangle{Width: 3, Height: 4}

	// Interface slice
	shapes := []Shape{circle, rect}
	for _, s := range shapes {
		printShapeInfo(s)
	}

	// Pointer receiver method
	c := &Circle{Radius: 2}
	c.Scale(3)
	fmt.Printf("Scaled circle area: %.2f\\n", c.Area())

	// Empty interface and type switch
	var v interface{} = 42
	switch val := v.(type) {
	case int:
		fmt.Println("int:", val)
	case string:
		fmt.Println("string:", val)
	default:
		fmt.Println("unknown type")
	}
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 2. GOROUTINES & CONCURRENCY
    # ═══════════════════════════════════════════════════════════
    ("go/goroutines-concurrency.md", "go", ["pattern", "concurrency"],
     "Goroutines & Concurrency",
     "Spawning goroutines, sync.WaitGroup for coordination, and goroutine lifecycle management.",
     "pattern",
     """package main

import (
	"fmt"
	"math/rand"
	"sync"
	"time"
)

// worker simulates processing an item.
func worker(id int, jobs <-chan int, wg *sync.WaitGroup) {
	defer wg.Done()
	for job := range jobs {
		// Simulate work
		delay := time.Duration(rand.Intn(200)) * time.Millisecond
		time.Sleep(delay)
		fmt.Printf("Worker %d processed job %d (took %v)\\n", id, job, delay)
	}
}

func main() {
	const numWorkers = 3
	const numJobs = 10

	jobs := make(chan int, numJobs)
	var wg sync.WaitGroup

	// Start workers
	for i := 1; i <= numWorkers; i++ {
		wg.Add(1)
		go worker(i, jobs, &wg)
	}

	// Send jobs
	for j := 1; j <= numJobs; j++ {
		jobs <- j
	}
	close(jobs) // Signals workers no more jobs

	// Wait for all workers to finish
	wg.Wait()
	fmt.Println("All jobs completed.")
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 3. CHANNELS
    # ═══════════════════════════════════════════════════════════
    ("go/channels.md", "go", ["pattern", "concurrency"],
     "Channels",
     "Buffered/unbuffered channels, select multiplexing, range, close, and directional channel parameters.",
     "pattern",
     """package main

import (
	"fmt"
	"time"
)

// producer sends values into a send-only channel.
func producer(out chan<- int) {
	for i := 1; i <= 5; i++ {
		fmt.Printf("Producing %d\\n", i)
		out <- i
		time.Sleep(100 * time.Millisecond)
	}
	close(out)
}

// consumer reads from a receive-only channel.
func consumer(in <-chan int, done chan<- bool) {
	for val := range in {
		fmt.Printf("Consumed %d\\n", val)
	}
	done <- true
}

func main() {
	// Unbuffered channel
	unbuf := make(chan int)
	go func() {
		unbuf <- 42
	}()
	fmt.Println("Unbuffered received:", <-unbuf)

	// Buffered channel
	buf := make(chan string, 3)
	buf <- "a"
	buf <- "b"
	buf <- "c"
	fmt.Println(<-buf, <-buf, <-buf)

	// Channel direction and range
	ch := make(chan int)
	done := make(chan bool)
	go producer(ch)
	go consumer(ch, done)
	<-done

	// Select multiplexing
	c1 := make(chan string, 1)
	c2 := make(chan string, 1)

	c1 <- "one"
	go func() {
		time.Sleep(50 * time.Millisecond)
		c2 <- "two"
	}()

	select {
	case msg := <-c1:
		fmt.Println("From c1:", msg)
	case msg := <-c2:
		fmt.Println("From c2:", msg)
	case <-time.After(100 * time.Millisecond):
		fmt.Println("Timeout")
	}
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 4. ERROR HANDLING
    # ═══════════════════════════════════════════════════════════
    ("go/error-handling.md", "go", ["pattern", "util"],
     "Error Handling",
     "The error interface, fmt.Errorf with %w wrapping, errors.Is/As, sentinel errors, and custom error types.",
     "pattern",
     """package main

import (
	"errors"
	"fmt"
	"os"
)

// --- Sentinel errors ---

var ErrNotFound = errors.New("item not found")
var ErrPermission = errors.New("permission denied")

// --- Custom error type ---

type ValidationError struct {
	Field   string
	Message string
}

func (e *ValidationError) Error() string {
	return fmt.Sprintf("validation failed on %s: %s", e.Field, e.Message)
}

func (e *ValidationError) Unwrap() error {
	return fmt.Errorf("field %s: %s", e.Field, e.Message)
}

// --- Functions returning wrapped errors ---

func findUser(id int) (string, error) {
	if id <= 0 {
		return "", &ValidationError{Field: "id", Message: "must be positive"}
	}
	if id > 100 {
		return "", fmt.Errorf("find user %d: %w", id, ErrNotFound)
	}
	return "Alice", nil
}

func loadConfig(path string) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("loading config %s: %w", path, err)
	}
	_ = data
	return nil
}

// --- Error inspection ---

func main() {
	// Sentinel error with errors.Is
	_, err := findUser(200)
	if errors.Is(err, ErrNotFound) {
		fmt.Println("Got expected not-found error")
	}

	// Custom error type with errors.As
	_, err = findUser(-1)
	var valErr *ValidationError
	if errors.As(err, &valErr) {
		fmt.Printf("Validation error on field %q: %s\\n", valErr.Field, valErr.Message)
	}

	// Wrapped error from stdlib
	err = loadConfig("/nonexistent/config.json")
	if err != nil {
		fmt.Println("Load error:", err)
		if errors.Is(err, os.ErrNotExist) {
			fmt.Println("  -> underlying: file does not exist")
		}
	}

	// Simple error check
	result, err := findUser(5)
	if err != nil {
		fmt.Println("Error:", err)
	} else {
		fmt.Println("Found:", result)
	}
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 5. JSON MARSHAL/UNMARSHAL
    # ═══════════════════════════════════════════════════════════
    ("go/json-marshal.md", "go", ["pattern", "io", "serialization"],
     "JSON Marshal/Unmarshal",
     "json.Marshal, json.Unmarshal, struct tags, custom MarshalJSON/UnmarshalJSON, and streaming with Encoder/Decoder.",
     "pattern",
     """package main

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
	fmt.Printf("Unmarshal: %+v\\n", p2)

	// Custom marshalling
	u := User{Username: "alice", Password: "supersecret123"}
	data, _ = json.Marshal(u)
	fmt.Println("Custom marshal:", string(data))

	var u2 User
	json.Unmarshal([]byte(`{"username":"bob","password":"mypassword123"}`), &u2)
	fmt.Printf("Custom unmarshal: %+v\\n", u2)

	// Streaming with Decoder
	reader := strings.NewReader(`{"name":"Eve","age":28}`)
	var p3 Person
	if err := json.NewDecoder(reader).Decode(&p3); err != nil {
		panic(err)
	}
	fmt.Printf("Stream decoded: %+v\\n", p3)

	// Streaming with Encoder
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	enc.Encode(map[string]interface{}{"status": "ok", "count": 42})
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 6. FLAGS & CLI
    # ═══════════════════════════════════════════════════════════
    ("go/flags-cli.md", "go", ["pattern", "cli", "util"],
     "Flags & CLI",
     "Parsing command-line flags with the flag package, os.Args, environment variables, and subcommands.",
     "pattern",
     """package main

import (
	"flag"
	"fmt"
	"os"
	"strconv"
	"strings"
)

// --- Subcommand-style flag parsing ---

type Config struct {
	Verbose bool
	Output  string
	Count   int
	Port    int
}

func main() {
	// Define flags
	verbose := flag.Bool("v", false, "verbose output")
	output := flag.String("o", "out.txt", "output file path")
	count := flag.Int("n", 1, "number of iterations")
	port := flag.Int("port", 8080, "server port")

	// Custom usage
	flag.Usage = func() {
		fmt.Fprintf(os.Stderr, "Usage: %s [options] [args...]\\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "Options:\\n")
		flag.PrintDefaults()
	}

	flag.Parse()

	// Populate config
	cfg := Config{
		Verbose: *verbose,
		Output:  *output,
		Count:   *count,
		Port:    *port,
	}

	// Environment override
	if v := os.Getenv("APP_PORT"); v != "" {
		if p, err := strconv.Atoi(v); err == nil {
			cfg.Port = p
		}
	}
	if v := os.Getenv("APP_VERBOSE"); v == "1" || strings.EqualFold(v, "true") {
		cfg.Verbose = true
	}

	// Remaining positional args
	args := flag.Args()

	if cfg.Verbose {
		fmt.Printf("Config: %+v\\n", cfg)
		fmt.Printf("Positional args: %v\\n", args)
	}

	fmt.Printf("Running on port %d with output %s\\n", cfg.Port, cfg.Output)
	for i := 0; i < cfg.Count; i++ {
		fmt.Printf("Iteration %d\\n", i+1)
	}
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 7. HTTP CLIENT
    # ═══════════════════════════════════════════════════════════
    ("go/http-client.md", "go", ["pattern", "web", "net"],
     "HTTP Client",
     "http.Get/Post/Do, custom headers, timeouts, JSON request/response decoding, and client configuration.",
     "pattern",
     """package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"time"
)

type Todo struct {
	UserID int    `json:"userId"`
	ID     int    `json:"id"`
	Title  string `json:"title"`
	Done   bool   `json:"completed"`
}

// --- Custom HTTP client ---

func newHTTPClient(timeout time.Duration) *http.Client {
	return &http.Client{
		Timeout: timeout,
		Transport: &http.Transport{
			MaxIdleConns:        10,
			IdleConnTimeout:     30 * time.Second,
			DisableCompression:  false,
		},
	}
}

// getJSON performs a GET and decodes JSON into target.
func getJSON(ctx context.Context, client *http.Client, url string, target interface{}) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return fmt.Errorf("creating request: %w", err)
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", "go-http-client/1.0")

	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("executing request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("unexpected status %d: %s", resp.StatusCode, string(body))
	}

	if err := json.NewDecoder(resp.Body).Decode(target); err != nil {
		return fmt.Errorf("decoding response: %w", err)
	}
	return nil
}

// postJSON sends a POST with JSON body and decodes the response.
func postJSON(ctx context.Context, client *http.Client, url string, payload, target interface{}) error {
	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshalling payload: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("creating request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("executing request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("request failed with %d: %s", resp.StatusCode, string(body))
	}

	if target != nil {
		if err := json.NewDecoder(resp.Body).Decode(target); err != nil {
			return fmt.Errorf("decoding response: %w", err)
		}
	}
	return nil
}

func main() {
	client := newHTTPClient(10 * time.Second)
	ctx := context.Background()

	// GET request
	var todo Todo
	if err := getJSON(ctx, client, "https://jsonplaceholder.typicode.com/todos/1", &todo); err != nil {
		log.Fatal(err)
	}
	fmt.Printf("GET /todos/1: %+v\\n", todo)

	// POST request
	newTodo := map[string]interface{}{
		"title":  "foo",
		"body":   "bar",
		"userId": 1,
	}
	var created map[string]interface{}
	if err := postJSON(ctx, client, "https://jsonplaceholder.typicode.com/todos", newTodo, &created); err != nil {
		log.Fatal(err)
	}
	fmt.Printf("POST response: %+v\\n", created)
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 8. TESTING & BENCHMARKS
    # ═══════════════════════════════════════════════════════════
    ("go/testing-benchmarks.md", "go", ["pattern", "test"],
     "Testing & Benchmarks",
     "Go test patterns: table-driven tests, subtests, helper assertions, and benchmarks with b *testing.B.",
     "pattern",
     """package main

import (
	"errors"
	"sort"
	"strings"
	"testing"
)

// --- Functions to test ---

func Sum(nums []int) int {
	total := 0
	for _, n := range nums {
		total += n
	}
	return total
}

func FilterEven(nums []int) []int {
	var result []int
	for _, n := range nums {
		if n%2 == 0 {
			result = append(result, n)
		}
	}
	return result
}

func Reverse(s string) (string, error) {
	if s == "" {
		return "", errors.New("empty string")
	}
	runes := []rune(s)
	for i, j := 0, len(runes)-1; i < j; i, j = i+1, j-1 {
		runes[i], runes[j] = runes[j], runes[i]
	}
	return string(runes), nil
}

// --- Table-driven tests ---

func TestSum(t *testing.T) {
	tests := []struct {
		name string
		nums []int
		want int
	}{
		{"empty", nil, 0},
		{"single", []int{5}, 5},
		{"multiple", []int{1, 2, 3, 4, 5}, 15},
		{"negatives", []int{-1, -2, -3}, -6},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := Sum(tt.nums)
			if got != tt.want {
				t.Errorf("Sum(%v) = %d; want %d", tt.nums, got, tt.want)
			}
		})
	}
}

func TestFilterEven(t *testing.T) {
	got := FilterEven([]int{1, 2, 3, 4, 5, 6})
	want := []int{2, 4, 6}
	if !equalSlice(got, want) {
		t.Errorf("FilterEven = %v; want %v", got, want)
	}
}

func TestReverse(t *testing.T) {
	tests := []struct {
		input string
		want  string
		err   bool
	}{
		{"hello", "olleh", false},
		{"a", "a", false},
		{"", "", true},
	}
	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			got, err := Reverse(tt.input)
			if (err != nil) != tt.err {
				t.Fatalf("Reverse(%q) error = %v; want error=%v", tt.input, err, tt.err)
			}
			if got != tt.want {
				t.Errorf("Reverse(%q) = %q; want %q", tt.input, got, tt.want)
			}
		})
	}
}

// --- Helper ---

func equalSlice(a, b []int) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

// --- Benchmark ---

func BenchmarkSum(b *testing.B) {
	nums := []int{1, 2, 3, 4, 5, 10, 20, 30, 40, 50}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		Sum(nums)
	}
}

func BenchmarkSortStrings(b *testing.B) {
	data := []string{"zebra", "apple", "monkey", "dog", "cat"}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		sort.Strings(data)
	}
}

func BenchmarkStringConcat(b *testing.B) {
	parts := []string{"a", "b", "c", "d", "e", "f", "g", "h"}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		var s string
		for _, p := range parts {
			s += p
		}
		_ = s
	}
}

func BenchmarkStringBuilder(b *testing.B) {
	parts := []string{"a", "b", "c", "d", "e", "f", "g", "h"}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		var sb strings.Builder
		for _, p := range parts {
			sb.WriteString(p)
		}
		_ = sb.String()
	}
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 9. SQL DATABASE
    # ═══════════════════════════════════════════════════════════
    ("go/sql-database.md", "go", ["pattern", "db", "sql"],
     "SQL Database",
     "database/sql with sql.Open, Query, Exec, prepared statements, rows.Scan, and transactions.",
     "pattern",
     """package main

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
	fmt.Printf("Created: %+v\\n", u)
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 10. CONTEXT & TIMEOUTS
    # ═══════════════════════════════════════════════════════════
    ("go/context-timeouts.md", "go", ["pattern", "concurrency", "net"],
     "Context & Timeouts",
     "context.WithCancel, WithTimeout, WithValue, ctx.Done channel, and graceful HTTP server shutdown.",
     "pattern",
     """package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

// --- Context with timeout ---

func slowOperation(ctx context.Context) (string, error) {
	// Simulate slow work
	select {
	case <-time.After(2 * time.Second):
		return "completed", nil
	case <-ctx.Done():
		return "", ctx.Err()
	}
}

// --- Context with cancellation ---

func worker(ctx context.Context, id int) {
	for {
		select {
		case <-ctx.Done():
			fmt.Printf("Worker %d shutting down: %v\\n", id, ctx.Err())
			return
		default:
			fmt.Printf("Worker %d working...\\n", id)
			time.Sleep(500 * time.Millisecond)
		}
	}
}

// --- Context with values ---

type contextKey string

const userIDKey contextKey = "user_id"

func authenticatedHandler(ctx context.Context) {
	if uid, ok := ctx.Value(userIDKey).(int); ok {
		fmt.Printf("Authenticated as user %d\\n", uid)
	} else {
		fmt.Println("Not authenticated")
	}
}

// --- HTTP server with graceful shutdown ---

func main() {
	// 1. Timeout
	ctx, cancel := context.WithTimeout(context.Background(), 1*time.Second)
	defer cancel()

	result, err := slowOperation(ctx)
	if err != nil {
		fmt.Println("Operation failed:", err)
	} else {
		fmt.Println("Result:", result)
	}

	// 2. Cancel propagation
	ctx2, cancel2 := context.WithCancel(context.Background())
	go worker(ctx2, 1)
	go worker(ctx2, 2)
	time.Sleep(1 * time.Second)
	cancel2() // signal all workers to stop
	time.Sleep(100 * time.Millisecond)

	// 3. Context values
	ctx3 := context.WithValue(context.Background(), userIDKey, 42)
	authenticatedHandler(ctx3)

	// 4. Graceful HTTP shutdown
	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintln(w, "Hello!")
	})

	srv := &http.Server{Addr: ":8080", Handler: mux}

	go func() {
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("HTTP serve: %v", err)
		}
	}()

	// Wait for interrupt signal
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	<-sig

	// Graceful shutdown with timeout
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	if err := srv.Shutdown(shutdownCtx); err != nil {
		log.Fatalf("Server shutdown: %v", err)
	}
	fmt.Println("Server stopped gracefully")
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 11. SYNC PRIMITIVES
    # ═══════════════════════════════════════════════════════════
    ("go/sync-primitives.md", "go", ["pattern", "concurrency"],
     "Sync Primitives",
     "sync.Mutex, sync.RWMutex, sync.Once, sync.Map, and atomic operations for safe concurrent access.",
     "pattern",
     """package main

import (
	"fmt"
	"sync"
	"sync/atomic"
	"time"
)

// --- Mutex-guarded counter ---

type SafeCounter struct {
	mu    sync.Mutex
	value int
}

func (c *SafeCounter) Increment() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.value++
}

func (c *SafeCounter) Value() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.value
}

// --- RWMutex for read-heavy workloads ---

type Cache struct {
	mu    sync.RWMutex
	store map[string]string
}

func NewCache() *Cache {
	return &Cache{store: make(map[string]string)}
}

func (c *Cache) Get(key string) (string, bool) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	v, ok := c.store[key]
	return v, ok
}

func (c *Cache) Set(key, value string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.store[key] = value
}

// --- sync.Once for lazy init ---

var (
	config     map[string]string
	configOnce sync.Once
)

func loadConfig() map[string]string {
	configOnce.Do(func() {
		fmt.Println("Loading config (once)...")
		config = map[string]string{
			"host": "localhost",
			"port": "8080",
		}
	})
	return config
}

// --- Atomic counter ---

type AtomicCounter struct {
	value int64
}

func (c *AtomicCounter) Add(delta int64) {
	atomic.AddInt64(&c.value, delta)
}

func (c *AtomicCounter) Value() int64 {
	return atomic.LoadInt64(&c.value)
}

func (c *AtomicCounter) Swap(new int64) int64 {
	return atomic.SwapInt64(&c.value, new)
}

// --- sync.Map for concurrent map ---

func main() {
	// Mutex counter
	var sc SafeCounter
	var wg sync.WaitGroup
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			sc.Increment()
		}()
	}
	wg.Wait()
	fmt.Println("SafeCounter:", sc.Value())

	// RWMutex cache
	cache := NewCache()
	cache.Set("key1", "value1")
	if v, ok := cache.Get("key1"); ok {
		fmt.Println("Cache get:", v)
	}

	// Once
	for i := 0; i < 3; i++ {
		go loadConfig()
	}

	// Atomic
	var ac AtomicCounter
	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			ac.Add(1)
		}()
	}
	wg.Wait()
	fmt.Println("AtomicCounter:", ac.Value())

	// sync.Map
	var sm sync.Map
	sm.Store("a", 1)
	sm.Store("b", 2)
	sm.Range(func(key, value interface{}) bool {
		fmt.Printf("sync.Map %v = %v\\n", key, value)
		return true
	})

	time.Sleep(50 * time.Millisecond) // let goroutines finish
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 12. SLICES & MAPS
    # ═══════════════════════════════════════════════════════════
    ("go/slices-maps.md", "go", ["pattern", "data-structure"],
     "Slices & Maps",
     "make, append, copy, delete, sort, range, composite literals, and common slice/map idioms.",
     "pattern",
     """package main

import (
	"fmt"
	"sort"
)

func main() {
	// --- Composite literals ---
	nums := []int{3, 1, 4, 1, 5, 9, 2, 6}
	grades := map[string]int{
		"Alice": 90,
		"Bob":   85,
		"Carol": 92,
	}

	fmt.Println("nums:", nums)
	fmt.Println("grades:", grades)

	// --- make, append, copy ---
	// make with length and capacity
	s := make([]int, 0, 10)
	s = append(s, 1, 2, 3, 4, 5)
	fmt.Println("slice:", s, "len:", len(s), "cap:", cap(s))

	// append variadic
	s = append(s, []int{6, 7, 8}...)
	fmt.Println("after append:", s)

	// copy
	dest := make([]int, len(s))
	n := copy(dest, s)
	fmt.Printf("copied %d elements: %v\\n", n, dest)

	// --- Slice operations ---
	// Sub-slice
	sub := nums[2:5]
	fmt.Println("nums[2:5]:", sub)

	// Delete element (idiomatic)
	i := 2 // index to delete
	nums = append(nums[:i], nums[i+1:]...)
	fmt.Println("after delete index 2:", nums)

	// Filter
	even := nums[:0]
	for _, v := range nums {
		if v%2 == 0 {
			even = append(even, v)
		}
	}
	nums = even
	fmt.Println("filtered even:", nums)

	// --- Map operations ---
	// Check existence
	if grade, ok := grades["Alice"]; ok {
		fmt.Println("Alice's grade:", grade)
	}

	// Delete
	delete(grades, "Bob")
	fmt.Println("after delete Bob:", grades)

	// Iterate over map
	for name, grade := range grades {
		fmt.Printf("  %s: %d\\n", name, grade)
	}

	// --- Sorting ---
	strs := []string{"zebra", "apple", "monkey", "dog"}
	sort.Strings(strs)
	fmt.Println("sorted strings:", strs)

	ints := []int{42, 3, 17, 8, 99}
	sort.Ints(ints)
	fmt.Println("sorted ints:", ints)

	// Sort slice of structs
	people := []struct {
		Name string
		Age  int
	}{
		{"Alice", 30},
		{"Bob", 25},
		{"Carol", 35},
	}
	sort.Slice(people, func(i, j int) bool {
		return people[i].Age < people[j].Age
	})
	fmt.Println("sorted by age:", people)

	// Reverse sort
	sort.Sort(sort.Reverse(sort.IntSlice(ints)))
	fmt.Println("reversed ints:", ints)

	// --- Transformations ---
	// Map (transform each element)
	doubled := make([]int, len(nums))
	for i, v := range nums {
		doubled[i] = v * 2
	}
	fmt.Println("doubled:", doubled)

	// Reduce (sum)
	sum := 0
	for _, v := range nums {
		sum += v
	}
	fmt.Println("sum:", sum)
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 13. TEMPLATES
    # ═══════════════════════════════════════════════════════════
    ("go/templates.md", "go", ["pattern", "util", "web"],
     "Templates",
     "text/template and html/template parsing, execution, template functions, and nested templates.",
     "pattern",
     """package main

import (
	"bytes"
	"fmt"
	"html/template"
	"os"
	"strings"
	"text/template"
)

// --- Custom template functions ---

var funcMap = template.FuncMap{
	"upper": strings.ToUpper,
	"lower": strings.ToLower,
	"greet": func(name string) string {
		return fmt.Sprintf("Hello, %s!", name)
	},
	"add": func(a, b int) int {
		return a + b
	},
}

// --- Text templates ---

const textTmpl = `
{{- /* This is a comment */ -}}
Report: {{.Title}}
{{- if .Items}}
Items ({{len .Items}}):
{{range .Items}}  - {{.Name | upper}}: {{.Value | printf "$%.2f"}}
{{end}}{{else}}
No items found.
{{end}}
Generated: {{.Generated | dateFormat}}
`

func dateFormat(t string) string {
	return t[:10] // simple formatting helper
}

// --- HTML templates (auto-escaped) ---

const htmlTmpl = `<!DOCTYPE html>
<html>
<head><title>{{.Title}}</title></head>
<body>
	<h1>{{.Title}}</h1>
	{{if .Items}}
	<ul>
	{{range .Items}}
		<li>{{.Name | upper}}: {{.Value | printf "$%.2f"}}</li>
	{{end}}
	</ul>
	{{else}}
	<p>No items.</p>
	{{end}}
	<p>User input: {{.UserInput}}</p>
</body>
</html>`

type Item struct {
	Name  string
	Value float64
}

type Data struct {
	Title     string
	Items     []Item
	Generated string
	UserInput string
}

func main() {
	data := Data{
		Title: "Monthly Report",
		Items: []Item{
			{Name: "widget", Value: 19.99},
			{Name: "gadget", Value: 29.95},
			{Name: "doohickey", Value: 5.00},
		},
		Generated: "2026-06-05T12:00:00Z",
		UserInput: "<script>alert('xss')</script>",
	}

	// --- Text template ---
	tmpl := template.New("report").Funcs(template.FuncMap{
		"dateFormat": dateFormat,
		"upper":      strings.ToUpper,
	})
	tmpl = template.Must(tmpl.Parse(textTmpl))

	var buf bytes.Buffer
	if err := tmpl.Execute(&buf, data); err != nil {
		panic(err)
	}
	fmt.Println("=== TEXT TEMPLATE ===")
	fmt.Println(buf.String())

	// --- HTML template (auto-escaping!) ---
	htmlTmpl := template.Must(template.New("webpage").Funcs(funcMap).Parse(htmlTmpl))

	var htmlBuf bytes.Buffer
	if err := htmlTmpl.Execute(&htmlBuf, data); err != nil {
		panic(err)
	}
	fmt.Println("=== HTML TEMPLATE ===")
	fmt.Println(htmlBuf.String())

	// Write to file
	os.WriteFile("output.html", htmlBuf.Bytes(), 0644)
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 14. EMBEDDING
    # ═══════════════════════════════════════════════════════════
    ("go/embedding.md", "go", ["pattern", "io", "util"],
     "Embedding",
     "embed.FS with go:embed directive: embedding files, directories, and using embedded FS in tests.",
     "pattern",
     """package main

import (
	"embed"
	"fmt"
	"io/fs"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"text/template"
	"time"
)

//go:embed static/*
var staticFiles embed.FS

//go:embed config.yaml
var configYAML string

//go:embed templates/*
var templateFS embed.FS

// --- Embedded static file server ---

func main() {
	// Read embedded string
	fmt.Println("=== Embedded config.yaml ===")
	fmt.Println(configYAML[:100], "...")

	fmt.Println("\\n=== Embedded file listing ===")
	entries, _ := fs.ReadDir(staticFiles, "static")
	for _, e := range entries {
		info, _ := e.Info()
		fmt.Printf("  %s (%d bytes)\\n", e.Name(), info.Size())
	}

	// Read a specific embedded file
	data, _ := staticFiles.ReadFile("static/style.css")
	fmt.Printf("\\nstatic/style.css (%d bytes):\\n%s\\n", len(data), string(data[:100]))

	// Walk embedded directory
	fmt.Println("\\n=== Walk embedded FS ===")
	fs.WalkDir(staticFiles, ".", func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		info, _ := d.Info()
		fmt.Printf("  %s (%d bytes)\\n", path, info.Size())
		return nil
	})

	// Use embedded templates
	tmpl, _ := template.ParseFS(templateFS, "templates/*.tmpl")
	tmpl.Execute(os.Stdout, map[string]string{"Name": "Alice"})

	// Serve embedded static files via HTTP
	http.Handle("/static/", http.FileServer(http.FS(staticFiles)))
	fmt.Println("\\nServing embedded files on :8080/static/")

	// Write embedded files to disk (for init/setup)
	os.WriteFile("out_config.yaml", []byte(configYAML), 0644)

	// --- Extracting embedded files ---
	err := fs.WalkDir(staticFiles, ".", func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			return os.MkdirAll(path, 0755)
		}
		data, err := fs.ReadFile(staticFiles, path)
		if err != nil {
			return err
		}
		return os.WriteFile(path, data, 0644)
	})
	if err != nil {
		log.Fatal(err)
	}
}

//go:embed templates/*.tmpl
var templatesFS embed.FS

// --- Embedded test data ---
var _ = func() struct{} {
	// Verify embedded content at init time
	data, err := templatesFS.ReadFile("templates/base.tmpl")
	if err != nil {
		panic(fmt.Sprintf("missing embedded template: %v", err))
	}
	_ = data
	return struct{}{}
}()

// --- init-time use in tests ---
func loadEmbeddedFixture(name string) ([]byte, error) {
	return staticFiles.ReadFile(filepath.Join("static", name))
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 15. LOGGING
    # ═══════════════════════════════════════════════════════════
    ("go/logging.md", "go", ["pattern", "util"],
     "Logging",
     "Standard log package and log/slog structured logging with levels, custom writers, and JSON output.",
     "pattern",
     """package main

import (
	"bytes"
	"fmt"
	"io"
	"log"
	"log/slog"
	"os"
	"strings"
	"time"
)

// --- Custom log writer ---

type LogWriter struct {
	buf bytes.Buffer
}

func (w *LogWriter) Write(p []byte) (n int, err error) {
	n, err = w.buf.Write(p)
	// Also echo to stdout
	os.Stdout.Write(p)
	return
}

func (w *LogWriter) String() string {
	return w.buf.String()
}

// --- Structured logging with slog ---

func main() {
	// --- Basic log package ---
	log.Println("Basic log message")
	log.SetFlags(log.Ldate | log.Ltime | log.Lshortfile)
	log.Printf("User %s logged in from %s", "alice", "192.168.1.1")

	// Custom writer
	writer := &LogWriter{}
	logger := log.New(writer, "CUSTOM: ", log.LstdFlags)
	logger.Println("This goes to custom writer")
	fmt.Println("Captured:", writer.String())

	// --- slog structured logging ---

	// Default text handler
	slog.Info("Server starting",
		"port", 8080,
		"env", "production",
	)
	slog.Warn("Disk space low",
		"percent", 92.5,
		"mount", "/data",
	)
	slog.Error("Connection refused",
		"host", "db.example.com",
		"port", 5432,
		"retry", 3,
	)

	// JSON handler
	jsonHandler := slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelDebug,
		ReplaceAttr: func(groups []string, a slog.Attr) slog.Attr {
			// Redact sensitive fields
			if a.Key == "password" {
				return slog.String("password", "[REDACTED]")
			}
			return a
		},
	})
	jsonLogger := slog.New(jsonHandler)
	jsonLogger.Debug("Debug message", "key", "value")
	jsonLogger.Info("JSON format",
		"user", "alice",
		"action", "login",
		"password", "secret123", // will be redacted
	)

	// Leveled logging
	slog.SetLogLoggerLevel(slog.LevelWarn)
	slog.Debug("this won't appear") // filtered
	slog.Warn("this will appear")

	// Custom handler that filters and formats
	customHandler := slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
		ReplaceAttr: func(groups []string, a slog.Attr) slog.Attr {
			// Add timestamp in custom format
			if a.Key == "time" {
				if t, ok := a.Value.Any().(time.Time); ok {
					return slog.String("time", t.Format(time.RFC3339))
				}
			}
			return a
		},
	})
	customLogger := slog.New(customHandler)
	customLogger.Info("Custom formatted log", "module", "api")

	// --- Multi-writer ---
	var logBuf bytes.Buffer
	multiWriter := io.MultiWriter(os.Stdout, &logBuf)
	slogger := slog.New(slog.NewTextHandler(multiWriter, nil))
	slogger.Info("Multi-writer test")
	fmt.Println("Buffer contains:", logBuf.String()[:50]+"...")

	// --- Logger with group ---
	groupLogger := slog.With(
		slog.Group("request",
			"id", "req-123",
			"method", "GET",
			"path", "/api/users",
		),
	)
	groupLogger.Info("Request handled", "status", 200)

	// Strings check to suppress "unused" warning
	_ = strings.Contains("test", "es")
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 16. TIME & DATE
    # ═══════════════════════════════════════════════════════════
    ("go/time-date.md", "go", ["pattern", "util"],
     "Time & Date",
     "time.Now, time.Parse/Format, time.Duration, time.Ticker, time.After, and timezone handling.",
     "pattern",
     """package main

import (
	"fmt"
	"time"
)

func main() {
	// --- Current time ---
	now := time.Now()
	fmt.Println("Now:", now)
	fmt.Println("Unix:", now.Unix())
	fmt.Println("UnixNano:", now.UnixNano())

	// --- Date components ---
	fmt.Printf("Year: %d, Month: %s, Day: %d\\n", now.Year(), now.Month(), now.Day())
	fmt.Printf("Hour: %d, Minute: %d, Second: %d\\n", now.Hour(), now.Minute(), now.Second())
	fmt.Println("Weekday:", now.Weekday())

	// --- Parsing ---
	// Go uses a reference time: Mon Jan 2 15:04:05 MST 2006
	parsed, err := time.Parse("2006-01-02", "2026-06-05")
	if err != nil {
		panic(err)
	}
	fmt.Println("Parsed date:", parsed)

	parsed2, _ := time.Parse(time.RFC3339, "2026-06-05T15:04:05Z")
	fmt.Println("Parsed RFC3339:", parsed2)

	// Flexible parsing using multiple layouts
	formats := []string{
		"2006-01-02",
		"2006-01-02T15:04:05Z07:00",
		time.RFC1123,
		"Jan 2, 2006",
	}
	for _, layout := range formats {
		if t, err := time.Parse(layout, "Jun 5, 2026"); err == nil {
			fmt.Printf("Matched layout %q: %v\\n", layout, t)
		}
	}

	// --- Formatting ---
	fmt.Println("Format YYYY-MM-DD:", now.Format("2006-01-02"))
	fmt.Println("Format RFC3339:", now.Format(time.RFC3339))
	fmt.Println("Format custom:", now.Format("Monday, January 2, 2006 at 3:04 PM"))

	// --- Duration ---
	dur := 2*time.Hour + 30*time.Minute + 15*time.Second
	fmt.Println("Duration:", dur)
	fmt.Println("Minutes:", dur.Minutes())
	fmt.Println("Seconds:", dur.Seconds())
	fmt.Println("Milliseconds:", dur.Milliseconds())

	// Add/Subtract
	tomorrow := now.Add(24 * time.Hour)
	fmt.Println("Tomorrow:", tomorrow)
	lastWeek := now.Add(-7 * 24 * time.Hour)
	fmt.Println("Last week:", lastWeek)

	diff := tomorrow.Sub(now)
	fmt.Println("Difference:", diff)

	// --- Time comparison ---
	a := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	b := time.Date(2026, 6, 1, 0, 0, 0, 0, time.UTC)
	fmt.Println("a before b:", a.Before(b))
	fmt.Println("a after b:", a.After(b))
	fmt.Println("a equal b:", a.Equal(b))

	// --- Ticker ---
	ticker := time.NewTicker(100 * time.Millisecond)
	go func() {
		for t := range ticker.C {
			fmt.Println("Tick at:", t.Format("15:04:05.000"))
		}
	}()
	time.Sleep(350 * time.Millisecond)
	ticker.Stop()
	fmt.Println("Ticker stopped")

	// --- Timer / After ---
	time.AfterFunc(50*time.Millisecond, func() {
		fmt.Println("Timer fired!")
	})

	select {
	case <-time.After(100 * time.Millisecond):
		fmt.Println("100ms timeout elapsed")
	}

	// --- Timezone ---
	loc, _ := time.LoadLocation("America/New_York")
	nyTime := now.In(loc)
	fmt.Println("New York time:", nyTime)

	utcTime := now.UTC()
	fmt.Println("UTC time:", utcTime)
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 17. REFLECTION
    # ═══════════════════════════════════════════════════════════
    ("go/reflection.md", "go", ["pattern", "meta"],
     "Reflection",
     "reflect.TypeOf/ValueOf, Kind inspection, struct tags, dynamic field access and method calls.",
     "pattern",
     """package main

import (
	"fmt"
	"reflect"
	"strings"
)

type Config struct {
	Host    string `json:"host" env:"APP_HOST" default:"localhost"`
	Port    int    `json:"port" env:"APP_PORT" default:"8080"`
	Debug   bool   `json:"debug" env:"APP_DEBUG" default:"false"`
	Timeout int    `json:"timeout" env:"APP_TIMEOUT" default:"30"`
}

// --- Inspect struct tags ---

func inspectStruct(v interface{}) {
	t := reflect.TypeOf(v)
	if t.Kind() == reflect.Ptr {
		t = t.Elem()
	}

	fmt.Printf("Type: %s\\n", t.Name())
	for i := 0; i < t.NumField(); i++ {
		field := t.Field(i)
		fmt.Printf("  Field %d: %s (%s)\\n", i, field.Name, field.Type)
		fmt.Printf("    Tag json:  %q\\n", field.Tag.Get("json"))
		fmt.Printf("    Tag env:   %q\\n", field.Tag.Get("env"))
		fmt.Printf("    Tag default: %q\\n", field.Tag.Get("default"))
	}
}

// --- Set defaults from tags ---

func setDefaults(v interface{}) {
	val := reflect.ValueOf(v)
	if val.Kind() != reflect.Ptr || val.IsNil() {
		return
	}
	val = val.Elem()
	t := val.Type()

	for i := 0; i < t.NumField(); i++ {
		field := t.Field(i)
		defaultVal := field.Tag.Get("default")
		if defaultVal == "" {
			continue
		}

		f := val.Field(i)
		if !f.CanSet() {
			continue
		}

		switch f.Kind() {
		case reflect.String:
			if f.String() == "" {
				f.SetString(defaultVal)
			}
		case reflect.Int, reflect.Int64:
			if f.Int() == 0 {
				var v int64
				fmt.Sscanf(defaultVal, "%d", &v)
				f.SetInt(v)
			}
		case reflect.Bool:
			if !f.Bool() && defaultVal == "true" {
				f.SetBool(true)
			}
		}
	}
}

// --- Dynamic method call ---

type Calculator struct{}

func (Calculator) Add(a, b int) int {
	return a + b
}

func (Calculator) Multiply(a, b int) int {
	return a * b
}

func callMethod(obj interface{}, name string, args ...interface{}) []reflect.Value {
	val := reflect.ValueOf(obj)
	method := val.MethodByName(name)
	if !method.IsValid() {
		fmt.Printf("Method %s not found\\n", name)
		return nil
	}

	var inputs []reflect.Value
	for _, arg := range args {
		inputs = append(inputs, reflect.ValueOf(arg))
	}

	return method.Call(inputs)
}

// --- Dynamic field read/write ---

func setField(obj interface{}, name string, value interface{}) {
	val := reflect.ValueOf(obj)
	if val.Kind() == reflect.Ptr {
		val = val.Elem()
	}
	field := val.FieldByName(name)
	if !field.IsValid() {
		fmt.Printf("Field %s not found\\n", name)
		return
	}
	if field.CanSet() {
		field.Set(reflect.ValueOf(value))
	}
}

func getField(obj interface{}, name string) interface{} {
	val := reflect.ValueOf(obj)
	if val.Kind() == reflect.Ptr {
		val = val.Elem()
	}
	return val.FieldByName(name).Interface()
}

func main() {
	// Inspect struct
	cfg := Config{Host: "example.com"}
	inspectStruct(cfg)

	// Set defaults from tags
	setDefaults(&cfg)
	fmt.Printf("\\nAfter defaults: Host=%q Port=%d Debug=%v Timeout=%d\\n",
		cfg.Host, cfg.Port, cfg.Debug, cfg.Timeout)

	// Dynamic method call
	calc := Calculator{}
	result := callMethod(calc, "Add", 10, 20)
	if len(result) > 0 {
		fmt.Printf("\\n10 + 20 = %v\\n", result[0].Interface())
	}

	// Dynamic field access
	setField(&cfg, "Host", "updated.com")
	setField(&cfg, "Port", 9090)
	fmt.Printf("\\nAfter dynamic set: Host=%q Port=%d\\n",
		getField(&cfg, "Host"), getField(&cfg, "Port"))

	// Kind checking
	var x interface{} = 42
	v := reflect.ValueOf(x)
	fmt.Printf("\\nValue: %v, Kind: %s, Type: %s\\n", v, v.Kind(), v.Type())

	// Strings check
	_ = strings.Contains("test", "es")
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 18. NET (TCP/UDP)
    # ═══════════════════════════════════════════════════════════
    ("go/net-tcp-udp.md", "go", ["pattern", "net", "server"],
     "Net (TCP/UDP)",
     "net.Listen, net.Dial, TCP echo server/client, UDP server/client, and bufio for line-based I/O.",
     "pattern",
     """package main

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
	fmt.Fprintf(conn, "%s\\n", message)

	// Read response
	response, err := bufio.NewReader(conn).ReadString('\\n')
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
			fmt.Printf("UDP received from %s: %s\\n", addr, msg)
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
"""),

    # ═══════════════════════════════════════════════════════════
    # 19. CRYPTO
    # ═══════════════════════════════════════════════════════════
    ("go/crypto.md", "go", ["pattern", "crypto", "security"],
     "Crypto",
     "crypto/sha256, crypto/rand, crypto/aes, bcrypt password hashing, and HMAC signing.",
     "pattern",
     """package main

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
"""),

    # ═══════════════════════════════════════════════════════════
    # 20. BUILD TAGS & CONDITIONAL COMPILATION
    # ═══════════════════════════════════════════════════════════
    ("go/build-tags.md", "go", ["pattern", "build", "platform"],
     "Build Tags & Conditional Compilation",
     "//go:build directives, file naming conventions, platform-specific code, and build tag constraints.",
     "pattern",
     """package main

// This file compiles on all platforms; platform-specific logic
// is handled via build constraints in companion files.

// --- Build tag overview ---
//
// File naming conventions (automatically constrained):
//   *_linux.go    — Linux only
//   *_windows.go  — Windows only
//   *_darwin.go   — macOS only
//   *_unix.go     — Unix-like (Linux, macOS, *BSD, Solaris)
//   _test.go      — only in test builds (except *_test.go naming)
//
// Build tag syntax (at top of file, before package declaration):
//   //go:build linux
//   //go:build !windows
//   //go:build linux && amd64
//   //go:build linux || darwin
//   //go:build ignore              — file excluded from all builds
//
// Multiple tags (separate lines):
//   //go:build linux
//   //go:build cgo
//
// Common tags: linux, darwin, windows, unix, amd64, arm64, 386,
//   cgo, go1.18, go1.21, race, debug, test, ignore
//
// Custom tags (set at build time):
//   go build -tags "prod,enterprise"

// --- Conditional compilation with ! constraint ---

//go:build !prod

// DevConfig contains development-only settings.
var DevConfig = map[string]string{
	"log_level": "debug",
	"db_host":   "localhost",
}

// --- prod.go companion (would be separate file) ---
// //go:build prod
//
// package main
//
// var DevConfig = map[string]string{
// 	"log_level": "info",
// 	"db_host":   "prod.internal",
// }

// --- Function with multiple platform-specific implementations ---

// getDefaultPath returns the default config path (platform-specific).
// Real implementations live in *_unix.go / *_windows.go files.
func getDefaultPath() string {
	// Generic fallback; overridden per platform
	return "/etc/app/config.yaml"
}

// TODO: Companion files would define:
//
// File: config_unix.go
// //go:build !windows
// package main
// func getDefaultPath() string { return "/etc/app/config.yaml" }
//
// File: config_windows.go
// //go:build windows
// package main
// func getDefaultPath() string { return "C:\\\\ProgramData\\\\App\\\\config.yaml" }

// --- Feature flags via build tags ---

//go:build cgo

// WithCGO is true when CGO is enabled.
const WithCGO = true

// --- Version-gated feature ---

//go:build go1.21

// UseSlices is available in Go 1.21+ (uses slices package).
const UseSlices = true

func main() {
	println("Build tags demo")
	println("DevConfig:", DevConfig["log_level"])
	println("Default path:", getDefaultPath())
	println("WithCGO:", WithCGO)
	println("UseSlices:", UseSlices)
}
"""),
]
