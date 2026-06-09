"""
Swift (15) + Kotlin (15) — 30-snippet code-corpus module.

Each entry is a 7-tuple:
  (rel_path, language, tags, title, description, source, code)

rel_path always ends with .md.
"""

SNIPPETS = [
    # =========================================================================
    # SWIFT entries (15)
    # =========================================================================
    (
        "swift/classes-structs.md",
        "swift",
        ["swift", "class", "struct", "enum", "value-semantics", "reference-semantics", "mutating"],
        "Classes, Structs & Enums",
        "Demonstrates Swift value types (struct/enum) vs reference types (class), "
        "mutating methods, enum associated values, and how copying semantics differ.",
        "pattern",
        '''\
import Foundation

// MARK: - Value type (struct)
struct Point {
    var x: Double
    var y: Double

    mutating func translate(dx: Double, dy: Double) {
        x += dx
        y += dy
    }
}

// MARK: - Reference type (class)
class Person {
    let name: String
    var age: Int

    init(name: String, age: Int) {
        self.name = name
        self.age = age
    }

    func haveBirthday() { age += 1 }
}

// MARK: - Enum with associated values
enum NetworkResult {
    case success(data: Data)
    case failure(error: Error, statusCode: Int)
    case notModified

    var isSuccess: Bool {
        if case .success = self { return true }
        return false
    }
}

// Value semantics demo
var p1 = Point(x: 1, y: 2)
var p2 = p1          // independent copy
p2.translate(dx: 5, dy: 5)
print(p1)            // Point(x: 1.0, y: 2.0)
print(p2)            // Point(x: 6.0, y: 7.0)

// Reference semantics demo
let alice = Person(name: "Alice", age: 30)
let bob = alice      // same instance
bob.haveBirthday()
print(alice.age)     // 31 — aliased mutation
print(bob.age)       // 31
''',
    ),
    (
        "swift/optionals-safety.md",
        "swift",
        ["swift", "optional", "if-let", "guard-let", "nil-coalescing", "optional-chaining"],
        "Optionals & Safety",
        "Shows Swift's optional system: if-let, guard-let, nil-coalescing (??), "
        "optional chaining, and map/flatMap on Optional values.",
        "pattern",
        '''\
import Foundation

let dict: [String: Any] = ["name": "Alice", "age": 30, "email": nil]

// if-let binding
if let name = dict["name"] as? String {
    print("Name is \\(name)")
}

// guard-let (early exit)
func greet(_ user: [String: Any]) {
    guard let name = user["name"] as? String else { return }
    print("Hello, \\(name)!")
}

// nil coalescing
let displayName = (dict["name"] as? String) ?? "Guest"

// Optional chaining
let uppercased = (dict["name"] as? String)?.uppercased()

// map / flatMap on Optional
let length: Int? = (dict["name"] as? String).map(\\.count)
let doubled: Int? = length.flatMap { $0 > 0 ? $0 * 2 : nil }
''',
    ),
    (
        "swift/closures-hof.md",
        "swift",
        ["swift", "closure", "higher-order", "map", "filter", "reduce", "escaping"],
        "Closures & Higher-Order Functions",
        "Covers closure syntax, trailing closures, shorthand arguments ($0), "
        "map/filter/reduce on collections, and @escaping / @autoclosure attributes.",
        "pattern",
        '''\
import Foundation

let numbers = [1, 2, 3, 4, 5]

// Closure basics
let doubled = numbers.map { $0 * 2 }

// Trailing closure
let evens = numbers.filter { $0.isMultiple(of: 2) }

// reduce(into:) for accumulating
let grouped = numbers.reduce(into: [String: [Int]]()) { dict, n in
    let key = n.isMultiple(of: 2) ? "even" : "odd"
    dict[key, default: []].append(n)
}

// @escaping closure (stored for later)
final class CallbackStore {
    private var handlers: [(Int) -> Void] = []

    func addHandler(_ handler: @escaping (Int) -> Void) {
        handlers.append(handler)
    }

    func fireAll(value: Int) {
        handlers.forEach { $0(value) }
    }
}

// @autoclosure example
func assert(_ condition: @autoclosure () -> Bool) {
    if !condition() { fatalError("Assertion failed") }
}
assert(1 + 1 == 2)   // autoclosure defers evaluation
''',
    ),
    (
        "swift/async-await-concurrency.md",
        "swift",
        ["swift", "async", "await", "Task", "TaskGroup", "Actor", "MainActor", "concurrency"],
        "async/await & Concurrency",
        "Covers Swift structured concurrency: async/await functions, Task, TaskGroup, "
        "Actor isolation, MainActor, and async let bindings.",
        "pattern",
        '''\
import Foundation

// MARK: - Async function
func fetchUser(id: Int) async throws -> String {
    let url = URL(string: "https://api.example.com/user/\\(id)")!
    let (data, _) = try await URLSession.shared.data(from: url)
    return String(decoding: data, as: UTF8.self)
}

// MARK: - Actor for isolation
actor Counter {
    private var value = 0
    func increment() { value += 1 }
    func getValue() -> Int { value }
}

// MARK: - Async let & TaskGroup
func loadAll() async throws -> [String] {
    async let user1 = fetchUser(id: 1)
    async let user2 = fetchUser(id: 2)

    // TaskGroup — dynamic concurrency
    let extra: [String] = try await withThrowingTaskGroup(of: String.self) { group in
        for id in 3...5 {
            group.addTask { try await fetchUser(id: id) }
        }
        return try await group.reduce(into: []) { $0.append($1) }
    }

    let firstTwo = try await [user1, user2]
    return firstTwo + extra
}

// MARK: - MainActor
@MainActor
final class ViewModel {
    var name: String = ""

    func updateUI() async {
        let fetched = try? await fetchUser(id: 1)
        name = fetched ?? "—"
    }
}
''',
    ),
    (
        "swift/protocols-extensions.md",
        "swift",
        ["swift", "protocol", "extension", "associatedtype", "protocol-composition"],
        "Protocols & Protocol Extensions",
        "Protocol definition, default implementations via protocol extensions, "
        "associated types, and protocol composition with & syntax.",
        "pattern",
        '''\
import Foundation

// MARK: - Protocol declaration
protocol Identifiable {
    associatedtype ID: Hashable
    var id: ID { get }
}

// Default implementation via extension
extension Identifiable {
    var id: String { UUID().uuidString }
}

// Protocol composition
protocol Loggable: AnyObject {
    func log(_ message: String)
}

protocol Metricable {
    var metrics: [String: Double] { get }
}

typealias Monitored = Loggable & Metricable

// Conformance
final class Monitor: Monitored {
    var metrics: [String: Double] = [:]

    func log(_ message: String) {
        print("[Monitor] \\(message)")
    }
}

// Constrained extension
extension Collection where Element: Numeric {
    var sum: Element { reduce(0, +) }
}

print([1, 2, 3].sum)  // 6
''',
    ),
    (
        "swift/codable-json.md",
        "swift",
        ["swift", "Codable", "JSON", "JSONEncoder", "JSONDecoder", "CodingKeys", "serialization"],
        "Codable & JSON",
        "Shows Swift's Codable system: automatic conformance, custom CodingKeys, "
        "JSONEncoder/Decoder, snake-case conversion, and date strategies.",
        "pattern",
        '''\
import Foundation

// Automatic Codable
struct User: Codable {
    let id: Int
    let name: String
    let email: String?
}

// Custom CodingKeys
struct Article: Codable {
    let id: Int
    let title: String
    let publishedAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case publishedAt = "published_at"
    }
}

let encoder = JSONEncoder()
encoder.keyEncodingStrategy = .convertToSnakeCase
encoder.dateEncodingStrategy = .iso8601

let decoder = JSONDecoder()
decoder.keyDecodingStrategy = .convertFromSnakeCase
decoder.dateDecodingStrategy = .iso8601

let json = #"{"id":1,"name":"Alice","email":"alice@example.com"}"#
if let data = json.data(using: .utf8),
   let user = try? decoder.decode(User.self, from: data) {
    print(user.name)
}
''',
    ),
    (
        "swift/swiftui-basics.md",
        "swift",
        ["swift", "SwiftUI", "View", "State", "Binding", "ObservedObject", "modifier"],
        "SwiftUI Basics",
        "Covers fundamental SwiftUI patterns: View protocol, @State, @Binding, "
        "@ObservedObject, layout containers (VStack/HStack/ZStack), and common modifiers.",
        "pattern",
        '''\
import SwiftUI

// MARK: - Simple view with @State
struct CounterView: View {
    @State private var count = 0

    var body: some View {
        VStack(spacing: 16) {
            Text("Count: \\(count)")
                .font(.title)

            HStack {
                Button("-") { count -= 1 }
                Button("+") { count += 1 }
            }
            .buttonStyle(.borderedProminent)
        }
        .padding()
    }
}

// MARK: - Parent passing @Binding
struct ParentView: View {
    @State private var text = ""

    var body: some View {
        VStack {
            TextField("Type here", text: $text)
                .textFieldStyle(.roundedBorder)
            ChildView(text: $text)
        }
    }
}

struct ChildView: View {
    @Binding var text: String

    var body: some View {
        Text("You typed: \\(text)")
            .foregroundColor(.secondary)
    }
}

// MARK: - ObservableObject pattern
final class SettingsViewModel: ObservableObject {
    @Published var volume: Double = 0.5
}

struct SettingsView: View {
    @ObservedObject var viewModel: SettingsViewModel

    var body: some View {
        Slider(value: $viewModel.volume, in: 0...1)
    }
}
''',
    ),
    (
        "swift/error-handling.md",
        "swift",
        ["swift", "throws", "try", "catch", "Result", "Error", "custom-error"],
        "Error Handling",
        "Shows Swift error handling: Error protocol, throwing functions, do/try/catch, "
        "Result type, try? vs try!, and custom error enums.",
        "pattern",
        '''\
import Foundation

// MARK: - Custom error
enum FileError: Error, CustomStringConvertible {
    case notFound(path: String)
    case permissionDenied
    case corrupted(reason: String)

    var description: String {
        switch self {
        case .notFound(let path): return "File not found: \\(path)"
        case .permissionDenied:   return "Permission denied"
        case .corrupted(let r):   return "Corrupted: \\(r)"
        }
    }
}

// Throwing function
func readConfig(at path: String) throws -> String {
    guard FileManager.default.fileExists(atPath: path) else {
        throw FileError.notFound(path: path)
    }
    return try String(contentsOfFile: path, encoding: .utf8)
}

// do / try / catch
do {
    let content = try readConfig(at: "/etc/hosts")
    print(content)
} catch let error as FileError {
    print("File error: \\(error)")
} catch {
    print("Other error: \\(error.localizedDescription)")
}

// try? — optional result
if let content = try? readConfig(at: "/etc/hosts") {
    print("Got \\(content.count) bytes")
}

// Result type
func fetchConfig() -> Result<String, FileError> {
    Result { try readConfig(at: "/etc/hosts") }
}
''',
    ),
    (
        "swift/collections-iteration.md",
        "swift",
        ["swift", "Array", "Dictionary", "Set", "map", "filter", "compactMap", "reduce", "zip", "stride"],
        "Collections & Iteration",
        "Covers Swift collection types and functional iteration: map/filter/compactMap, "
        "forEach, zip, stride, reduce(into:), and Set operations.",
        "pattern",
        '''\
import Foundation

let words = ["swift", "rust", "kotlin", "python", "go"]

// map / compactMap
let uppercased = words.map { $0.uppercased() }
let lengths = words.compactMap { $0.count > 2 ? $0.count : nil }

// filter
let longWords = words.filter { $0.count > 4 }

// reduce(into:)
let groupedByFirst = words.reduce(into: [Character: [String]]()) { acc, w in
    guard let first = w.first else { return }
    acc[first, default: []].append(w)
}

// zip
let ranks = Array(1...words.count)
for (rank, word) in zip(ranks, words) {
    print("\\(rank). \\(word)")
}

// stride
for i in stride(from: 0, to: words.count, by: 2) {
    print(words[i])
}

// Set algebra
let a: Set = [1, 2, 3, 4]
let b: Set = [3, 4, 5, 6]
print(a.intersection(b))  // [3, 4]
print(a.symmetricDifference(b))  // [1, 2, 5, 6]

// forEach
words.forEach { print($0) }
''',
    ),
    (
        "swift/property-wrappers.md",
        "swift",
        ["swift", "property-wrapper", "Published", "AppStorage", "State", "custom-wrapper"],
        "Property Wrappers",
        "Shows Swift property wrappers: @Published, @AppStorage, @State, and "
        "building a custom property wrapper with projectedValue.",
        "pattern",
        '''\
import Foundation
import SwiftUI

// MARK: - Built-in wrappers

final class ViewModel: ObservableObject {
    @Published var isLoaded = false
}

struct SettingsView: View {
    @AppStorage("theme") var theme: String = "light"
    @State private var counter = 0

    var body: some View {
        Text("theme: \\(theme), count: \\(counter)")
    }
}

// MARK: - Custom property wrapper
@propertyWrapper
struct Clamped<T: Comparable> {
    private var value: T
    private let range: ClosedRange<T>

    init(wrappedValue: T, _ range: ClosedRange<T>) {
        self.range = range
        self.value = min(max(wrappedValue, range.lowerBound), range.upperBound)
    }

    var wrappedValue: T {
        get { value }
        set { value = min(max(newValue, range.lowerBound), range.upperBound) }
    }

    // projectedValue exposes the raw (unclamped) set
    var projectedValue: Self { self }
}

struct VideoPlayer {
    @Clamped(0.0...1.0) var volume: Double = 0.5

    mutating func setVolumeRaw(_ raw: Double) {
        $volume.wrappedValue = raw  // bypass clamping via projectedValue
    }
}
''',
    ),
    (
        "swift/file-io-data.md",
        "swift",
        ["swift", "FileManager", "JSONEncoder", "JSONDecoder", "Data", "Bundle", "file-io"],
        "File I/O & Data",
        "Shows reading/writing files with FileManager, encoding/decoding JSON to/from "
        "files, working with Data, Bundle resources, and String(contentsOf:).",
        "pattern",
        '''\
import Foundation

let fm = FileManager.default
let documents = fm.urls(for: .documentDirectory, in: .userDomainMask).first!
let fileURL = documents.appendingPathComponent("data.json")

// Writing JSON to file
struct Person: Codable {
    let name: String
    let age: Int
}

let people = [Person(name: "Alice", age: 30), Person(name: "Bob", age: 25)]

do {
    let data = try JSONEncoder().encode(people)
    try data.write(to: fileURL, options: .atomic)
} catch {
    print("Write error: \\(error)")
}

// Reading JSON from file
do {
    let data = try Data(contentsOf: fileURL)
    let decoded = try JSONDecoder().decode([Person].self, from: data)
    print(decoded)
} catch {
    print("Read error: \\(error)")
}

// Reading from Bundle
if let bundleURL = Bundle.main.url(forResource: "config", withExtension: "json"),
   let content = try? String(contentsOf: bundleURL, encoding: .utf8) {
    print(content)
}

// FileManager operations
let tempDir = fm.temporaryDirectory
let tempFile = tempDir.appendingPathComponent(UUID().uuidString + ".txt")
try? "hello".write(to: tempFile, atomically: true, encoding: .utf8)
try? fm.removeItem(at: tempFile)
''',
    ),
    (
        "swift/generics-associated-types.md",
        "swift",
        ["swift", "generic", "associatedtype", "where", "constraint"],
        "Generics & Associated Types",
        "Covers generic functions, generic types, associatedtype in protocols, "
        "and where clauses for type constraints.",
        "pattern",
        '''\
import Foundation

// Generic function
func swapValues<T>(_ a: inout T, _ b: inout T) {
    (a, b) = (b, a)
}

// Generic type with constraint
struct Stack<Element: Equatable> {
    private var storage: [Element] = []

    mutating func push(_ element: Element) { storage.append(element) }
    mutating func pop() -> Element? { storage.popLast() }
    func contains(_ element: Element) -> Bool { storage.contains(element) }
}

// Protocol with associatedtype
protocol Container {
    associatedtype Item
    mutating func append(_ item: Item)
    var count: Int { get }
}

// Generic conformance with where clause
extension Container where Item: Numeric {
    var total: Item { (0..<count).reduce(into: 0 as! Item) { _, _ in } }
}

// Concrete stack
var s = Stack<Int>()
s.push(1)
s.push(2)
print(s.contains(1))  // true

// where clause on function
func allEqual<T: Sequence>(_ seq: T) -> Bool where T.Element: Equatable {
    var iter = seq.makeIterator()
    guard let first = iter.next() else { return true }
    while let next = iter.next() {
        if first != next { return false }
    }
    return true
}
''',
    ),
    (
        "swift/keypaths-kvo.md",
        "swift",
        ["swift", "KeyPath", "WritableKeyPath", "KVO", "subscript", "observe"],
        "Key Paths & KVO",
        "Shows Swift key paths (\\KeyPath), WritableKeyPath, subscript access by key path, "
        "and Cocoa Key-Value Observing with NSObject.",
        "pattern",
        '''\
import Foundation

// KeyPath basics
struct Person {
    let name: String
    var age: Int
}

let alice = Person(name: "Alice", age: 30)
let namePath = \\Person.name
print(alice[keyPath: namePath])  // Alice

// WritableKeyPath
var bob = Person(name: "Bob", age: 25)
let agePath = \\Person.age
bob[keyPath: agePath] = 26
print(bob.age)  // 26

// KeyPaths as first-class values
func getValue<T, V>(_ obj: T, _ keyPath: KeyPath<T, V>) -> V {
    obj[keyPath: keyPath]
}
print(getValue(alice, \\.name))

// KVO with NSObject
final class ObservablePerson: NSObject {
    @objc dynamic var name: String
    @objc dynamic var age: Int

    init(name: String, age: Int) {
        self.name = name
        self.age = age
    }
}

let observed = ObservablePerson(name: "Charlie", age: 40)
let observation = observed.observe(\\.age, options: [.old, .new]) { obj, change in
    print("Age changed: \\(change.oldValue ?? 0) -> \\(change.newValue ?? 0)")
}
observed.age = 41
observation.invalidate()
''',
    ),
    (
        "swift/memory-arc.md",
        "swift",
        ["swift", "ARC", "weak", "unowned", "reference-cycle", "capture-list", "autoreleasepool"],
        "Memory & ARC",
        "Covers Automatic Reference Counting: weak/unowned references, "
        "reference cycles, capture lists in closures, and autoreleasepool.",
        "pattern",
        '''\
import Foundation

// MARK: - Strong reference cycle
class Parent {
    let name: String
    var child: Child?

    init(name: String) { self.name = name }
    deinit { print("\\(name) deinit") }
}

class Child {
    let name: String
    weak var parent: Parent?   // weak avoids cycle

    init(name: String) { self.name = name }
    deinit { print("\\(name) deinit") }
}

var parent: Parent? = Parent(name: "Dad")
var child: Child? = Child(name: "Son")
parent?.child = child
child?.parent = parent

parent = nil  // both deinit because parent is weakly referenced
child = nil

// MARK: - Capture lists
final class Logger {
    var message: String = "Hello"

    func makeClosure() -> () -> Void {
        // [weak self] avoids retain cycle
        return { [weak self] in
            guard let self else { return }
            print(self.message)
        }
    }
}

// MARK: - autoreleasepool
autoreleasepool {
    for i in 0..<1000 {
        let _ = String(format: "%d", i)
    }
}

// MARK: - unowned (use when self will outlive closure)
final class Service {
    var handler: (() -> Void)?

    func setup() {
        handler = { [unowned self] in
            print("Handling with \\(self)")
        }
    }
}
''',
    ),
    (
        "swift/package-manager.md",
        "swift",
        ["swift", "Package", "SwiftPM", "Package.swift", "dependencies", "targets", "products"],
        "Package Manager (SwiftPM)",
        "Shows a complete Package.swift manifest: dependencies, targets, products, "
        "and how to structure an SPM package with an executable and library.",
        "pattern",
        '''\
// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "MyLibrary",
    platforms: [
        .macOS(.v13),
        .iOS(.v16),
    ],
    products: [
        // Library product
        .library(
            name: "MyLibrary",
            targets: ["MyLibrary"]
        ),
        // Executable product
        .executable(
            name: "my-tool",
            targets: ["MyTool"]
        ),
    ],
    dependencies: [
        // Remote package dependency
        .package(url: "https://github.com/apple/swift-argument-parser",
                 from: "1.2.0"),
        // Local package dependency
        .package(path: "../LocalHelpers"),
    ],
    targets: [
        // Main library target
        .target(
            name: "MyLibrary",
            dependencies: [
                .product(name: "ArgumentParser",
                         package: "swift-argument-parser"),
            ],
            swiftSettings: [
                .enableUpcomingFeature("BareSlashRegexLiterals"),
            ]
        ),
        // Executable target
        .executableTarget(
            name: "MyTool",
            dependencies: ["MyLibrary"]
        ),
        // Test target
        .testTarget(
            name: "MyLibraryTests",
            dependencies: ["MyLibrary"]
        ),
    ]
)
''',
    ),
    # =========================================================================
    # KOTLIN entries (15)
    # =========================================================================
    (
        "kotlin/classes-oop.md",
        "kotlin",
        ["kotlin", "class", "data-class", "sealed-class", "object", "companion", "open", "abstract"],
        "Classes & OOP",
        "Covers Kotlin OOP: class, data class, sealed class, object declarations, "
        "companion objects, open/final, and abstract classes.",
        "pattern",
        '''\
import kotlin.random.Random

// Data class — automatic equals/hashCode/toString/copy
data class User(val id: Int, val name: String, val email: String? = null)

// Open class (extendable)
open class Animal(val name: String) {
    open fun speak(): String = "$name makes a sound"
}

class Dog(name: String) : Animal(name) {
    override fun speak(): String = "$name barks"
}

// Abstract class
abstract class Shape {
    abstract fun area(): Double
}

class Circle(val radius: Double) : Shape() {
    override fun area(): Double = Math.PI * radius * radius
}

// Sealed class — restricted hierarchy
sealed class NetworkResult {
    data class Success(val data: String) : NetworkResult()
    data class Error(val message: String) : NetworkResult()
    object Loading : NetworkResult()
}

// Object — singleton
object Config {
    val baseUrl = "https://api.example.com"
    fun timeout(): Long = 30_000
}

// Companion object — static-like members
class Database {
    companion object {
        private var instance: Database? = null
        fun getInstance(): Database =
            instance ?: Database().also { instance = it }
    }
}

fun main() {
    val user = User(1, "Alice")
    val dog = Dog("Rex")
    println(dog.speak())
}
''',
    ),
    (
        "kotlin/null-safety-elvis.md",
        "kotlin",
        ["kotlin", "nullable", "elvis", "safe-call", "let", "also", "apply", "run", "with"],
        "Null Safety & Elvis",
        "Shows Kotlin null safety: ? nullable types, ?. safe calls, !! not-null assertion, "
        "elvis ?:, and scope functions let/also/apply/run/with.",
        "pattern",
        '''\
data class Address(val street: String?, val city: String)
data class Person(val name: String, val address: Address?)

// Safe call operator
fun getCity(person: Person?): String? = person?.address?.city

// Elvis operator
fun getCityOrDefault(person: Person?): String =
    person?.address?.city ?: "Unknown"

// Not-null assertion (only when you're sure)
fun getCityForce(person: Person?): String =
    person!!.address!!.city

// let — execute if non-null
fun printCity(person: Person?) {
    person?.address?.city?.let { city ->
        println("City: $city")
    }
}

// also — side-effect chaining
val user = Person("Alice", Address("123 Main", "NYC")).also {
    println("Created user: ${it.name}")
}

// apply — configure object
val configured = Person("Bob", null).apply {
    // 'this' is the Person
}

// run — scoped result
val upper = person?.run {
    name.uppercase()
}

// with — non-extension scope
with(person) {
    println("Name: ${this?.name}")
}

fun main() {
    println(getCityOrDefault(Person("Alice", Address(null, "NYC"))))
    // Unknown
}
''',
    ),
    (
        "kotlin/coroutines-flow.md",
        "kotlin",
        ["kotlin", "coroutine", "launch", "async", "await", "runBlocking", "Flow", "collect", "StateFlow"],
        "Coroutines & Flow",
        "Covers Kotlin coroutines: launch, async/await, runBlocking, withContext, "
        "Flow builders, collect, and StateFlow for reactive state.",
        "pattern",
        '''\
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*

// Basic coroutine
suspend fun fetchUser(id: Int): String {
    delay(100) // simulate network
    return "User $id"
}

fun main() = runBlocking {
    // Launch (fire-and-forget)
    val job = launch {
        val user = fetchUser(1)
        println(user)
    }
    job.join()

    // Async/await (return a value)
    val deferred = async { fetchUser(2) }
    println(deferred.await())

    // withContext — switch dispatcher
    val result = withContext(Dispatchers.IO) {
        fetchUser(3)
    }

    // Flow — cold stream
    val numberFlow = flow {
        for (i in 1..3) {
            delay(100)
            emit(i)
        }
    }

    numberFlow
        .map { it * 2 }
        .filter { it > 2 }
        .collect { println(it) }

    // StateFlow — observable state
    val state = MutableStateFlow("initial")
    val job2 = launch {
        state.collect { println("State: $it") }
    }
    state.value = "updated"
    delay(50)
    job2.cancel()
}
''',
    ),
    (
        "kotlin/collections-sequences.md",
        "kotlin",
        ["kotlin", "listOf", "mapOf", "filter", "map", "fold", "groupBy", "chunked", "sequence"],
        "Collections & Sequences",
        "Covers Kotlin collection operations: listOf/mapOf, filter/map/fold/groupBy/chunked, "
        "Sequence for lazy evaluation, and common functional patterns.",
        "pattern",
        '''\
val numbers = listOf(1, 2, 3, 4, 5, 6)

// map / filter
val doubled = numbers.map { it * 2 }
val evens = numbers.filter { it % 2 == 0 }

// fold — accumulate
val sum = numbers.fold(0) { acc, n -> acc + n }

// groupBy
val grouped = numbers.groupBy { if (it % 2 == 0) "even" else "odd" }

// chunked — split into batches
val batches = numbers.chunked(2) // [[1,2], [3,4], [5,6]]

// Map operations
val map = mapOf("a" to 1, "b" to 2, "c" to 3)
val transformed = map.mapValues { (_, v) -> v * 2 }

// Sequence — lazy evaluation
val result = sequenceOf(1, 2, 3, 4, 5)
    .map {
        println("mapping $it")
        it * 2
    }
    .filter {
        println("filtering $it")
        it > 5
    }
    .toList() // terminal operation triggers evaluation

// flatMap
val nested = listOf(listOf(1, 2), listOf(3, 4))
val flattened = nested.flatMap { it }

// zipWithNext
val deltas = numbers.zipWithNext { a, b -> b - a }

fun main() {
    println(flattened) // [1, 2, 3, 4]
}
''',
    ),
    (
        "kotlin/functions-lambdas.md",
        "kotlin",
        ["kotlin", "lambda", "higher-order", "inline", "crossinline", "noinline", "extension-function"],
        "Functions & Lambdas",
        "Covers Kotlin functions: lambda syntax, 'it' implicit argument, higher-order functions, "
        "inline/crossinline/noinline modifiers, and extension functions.",
        "pattern",
        '''\
// Lambda basics
val square: (Int) -> Int = { x -> x * x }
val cube: (Int) -> Int = { it * it * it }

// Higher-order function
fun <T, R> List<T>.transform(block: (T) -> R): List<R> = map(block)

// Extension function
fun String.isPalindrome(): Boolean =
    this == reversed()

// Infix function
infix fun Int.plusTimes(other: Int): Int = (this + other) * 2

// Inline function
inline fun measureTime(block: () -> Unit): Long {
    val start = System.nanoTime()
    block()
    return System.nanoTime() - start
}

// crossinline — no non-local return
inline fun runWithLog(crossinline block: () -> Unit) {
    println("start")
    block()
    println("end")
}

// noinline — pass lambda as value
inline fun conditional(
    noinline body: () -> Unit,
    condition: Boolean
) {
    if (condition) body()
}

fun main() {
    println("Racecar".isPalindrome())   // true
    println(3 plusTimes 4)              // 14
    println(square(5))                  // 25
}
''',
    ),
    (
        "kotlin/ktor-http.md",
        "kotlin",
        ["kotlin", "Ktor", "embeddedServer", "routing", "get", "post", "content-negotiation", "client"],
        "Kotlin Ktor HTTP",
        "Shows a basic Ktor HTTP server with routing, content negotiation (JSON), "
        "and a Ktor client making requests.",
        "pattern",
        '''\
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
''',
    ),
    (
        "kotlin/extension-functions-properties.md",
        "kotlin",
        ["kotlin", "extension-function", "extension-property", "infix", "operator-overloading"],
        "Extension Functions & Properties",
        "Shows Kotlin extension functions, extension properties, infix notation, "
        "and operator overloading.",
        "pattern",
        '''\
// Extension function
fun String.wordCount(): Int =
    trim().split("\\s+".toRegex()).size

// Extension property
val String.isEmail: Boolean
    get() = matches(Regex("^[A-Za-z0-9+_.-]+@(.+)$"))

// Generic extension
fun <T> List<T>.secondOrNull(): T? =
    if (size >= 2) this[1] else null

// Infix extension
infix fun String.repeat(times: Int): String =
    buildString { repeat(times) { append(this@repeat) } }

// Operator overloading
data class Vector(val x: Int, val y: Int) {
    operator fun plus(other: Vector) = Vector(x + other.x, y + other.y)
    operator fun times(scalar: Int) = Vector(x * scalar, y * scalar)
    operator fun compareTo(other: Vector): Int =
        (x * x + y * y) compareTo (other.x * other.x + other.y * other.y)
}

fun main() {
    println("Hello world!".wordCount())       // 2
    println("test@example.com".isEmail)       // true
    println(listOf(1).secondOrNull())         // null

    println("ha" repeat 3)                    // hahaha

    val v1 = Vector(1, 2)
    val v2 = Vector(3, 4)
    println(v1 + v2)                          // Vector(x=4, y=6)
    println(v1 * 3)                           // Vector(x=3, y=6)
    println(v1 < v2)                          // true (shorter magnitude)
}
''',
    ),
    (
        "kotlin/sealed-classes-when.md",
        "kotlin",
        ["kotlin", "sealed-class", "sealed-interface", "when", "exhaustive", "Result"],
        "Sealed Classes & When",
        "Covers Kotlin sealed classes/interfaces, exhaustive when expressions, "
        "and the Result type for functional error handling.",
        "pattern",
        '''\
// Sealed interface (Kotlin 1.5+)
sealed interface ApiResponse<out T> {
    data class Success<T>(val data: T) : ApiResponse<T>
    data class Error(val message: String, val code: Int) : ApiResponse<Nothing>
    object Loading : ApiResponse<Nothing>
}

// Exhaustive when (compiler-enforced)
fun <T> handleResponse(response: ApiResponse<T>): String = when (response) {
    is ApiResponse.Success -> "Data: ${response.data}"
    is ApiResponse.Error -> "Error ${response.code}: ${response.message}"
    ApiResponse.Loading -> "Loading..."
    // No 'else' needed — sealed hierarchy is exhaustive
}

// Sealed class (classic form)
sealed class Either<out L, out R> {
    data class Left<L>(val value: L) : Either<L, Nothing>()
    data class Right<R>(val value: R) : Either<Nothing, R>()
}

fun parse(input: String): Either<Exception, Int> =
    try {
        Either.Right(input.toInt())
    } catch (e: NumberFormatException) {
        Either.Left(e)
    }

// Kotlin Result (built-in)
fun riskyOperation(): Result<String> = runCatching {
    if (Random.nextBoolean()) "success" else throw RuntimeException("fail")
}

fun main() {
    val res = riskyOperation()
    res
        .onSuccess { println("OK: $it") }
        .onFailure { println("FAIL: ${it.message}") }

    println(handleResponse(ApiResponse.Loading))

    when (parse("42")) {
        is Either.Left -> println("Parse error")
        is Either.Right -> println("Got number")
    }
}
''',
    ),
    (
        "kotlin/delegated-properties.md",
        "kotlin",
        ["kotlin", "delegated-property", "by-lazy", "Delegates.observable", "by-map", "Compose"],
        "Delegated Properties",
        "Shows Kotlin delegated properties: by lazy, Delegates.observable, "
        "by map, and by remember in Compose.",
        "pattern",
        '''\
import kotlin.properties.Delegates

// Lazy initialization — computed once on first access
val heavyComputation: String by lazy {
    println("Computing...")
    "Result: ${(1..100_000).sum()}"
}

// Observable delegate — fires on every change
var watched: String by Delegates.observable("initial") { _, old, new ->
    println("$old -> $new")
}

// Vetoable — can reject changes
var positive: Int by Delegates.vetoable(0) { _, _, new -> new >= 0 }

// Delegate to a Map (useful for deserialization)
class User(map: Map<String, Any?>) {
    val name: String by map
    val age: Int by map
}

// Custom delegate
class Logged<String> {
    private var value: String? = null

    operator fun getValue(thisRef: Any?, property: kotlin.reflect.KProperty<*>): String {
        println("GET ${property.name} = $value")
        return value ?: "default"
    }

    operator fun setValue(thisRef: Any?, property: kotlin.reflect.KProperty<*>, newValue: String) {
        println("SET ${property.name} = $newValue")
        value = newValue
    }
}

var logged by Logged<String>()

fun main() {
    println(heavyComputation)  // computes once
    println(heavyComputation)  // cached

    watched = "hello"          // initial -> hello
    watched = "world"          // hello -> world

    logged = "test"            // SET logged = test
    println(logged)            // GET logged = test

    val user = User(mapOf("name" to "Alice", "age" to 30))
    println(user.name)         // Alice
}
''',
    ),
    (
        "kotlin/jetpack-compose-basics.md",
        "kotlin",
        ["kotlin", "Compose", "Composable", "Column", "Row", "Box", "mutableStateOf", "LazyColumn"],
        "Jetpack Compose Basics",
        "Covers fundamental Jetpack Compose patterns: @Composable functions, "
        "Column/Row/Box layout, mutableStateOf, LazyColumn, and recomposition.",
        "pattern",
        '''\
import androidx.compose.runtime.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

// Simple composable
@Composable
fun Greeting(name: String) {
    Text(text = "Hello, $name!")
}

// State & recomposition
@Composable
fun Counter() {
    var count by remember { mutableStateOf(0) }

    Column(modifier = Modifier.padding(16.dp)) {
        Text("Count: $count", style = MaterialTheme.typography.headlineMedium)

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { count-- }) { Text("-") }
            Button(onClick = { count++ }) { Text("+") }
        }
    }
}

// LazyColumn (RecyclerView equivalent)
data class Item(val id: Int, val title: String)

@Composable
fun ItemList(items: List<Item>) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        items(items, key = { it.id }) { item ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Text(
                    text = item.title,
                    modifier = Modifier.padding(16.dp)
                )
            }
        }
    }
}
''',
    ),
    (
        "kotlin/dsl-builders.md",
        "kotlin",
        ["kotlin", "DSL", "type-safe-builder", "DslMarker", "receiver", "builder-pattern"],
        "DSL Builders",
        "Shows Kotlin type-safe DSL builders: receiver-based lambda, @DslMarker "
        "to restrict implicit receivers, and a practical HTML-like DSL example.",
        "pattern",
        '''\
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
''',
    ),
    (
        "kotlin/file-io-serialization.md",
        "kotlin",
        ["kotlin", "serialization", "Serializable", "Json", "file-io", "java.nio.file", "use"],
        "File I/O & Serialization",
        "Shows Kotlin I/O with java.nio.file, kotlinx.serialization for JSON, "
        "and the 'use' extension for Closeable resources.",
        "pattern",
        '''\
import kotlinx.serialization.*
import kotlinx.serialization.json.Json
import java.nio.file.*

@Serializable
data class Person(val name: String, val age: Int, val email: String? = null)

val json = Json { prettyPrint = true; ignoreUnknownKeys = true }

// Write JSON to file
fun writePeople(people: List<Person>, path: Path) {
    Files.writeString(path, json.encodeToString(people))
}

// Read JSON from file
fun readPeople(path: Path): List<Person> {
    val content = Files.readString(path)
    return json.decodeFromString<List<Person>>(content)
}

// 'use' for Closeable
fun readLines(path: Path): List<String> =
    Files.newBufferedReader(path).use { reader ->
        reader.readLines()
    }

// Walk directory tree
fun walkTree(root: Path): Sequence<Path> =
    Files.walk(root).use { it.toList().asSequence() }

fun main() {
    val dir = Path.of("/tmp/data")
    Files.createDirectories(dir)
    val file = dir.resolve("people.json")

    val people = listOf(
        Person("Alice", 30),
        Person("Bob", 25, "bob@example.com")
    )

    writePeople(people, file)
    val loaded = readPeople(file)
    println(loaded)

    // Cleanup
    Files.deleteIfExists(file)
}
''',
    ),
    (
        "kotlin/testing.md",
        "kotlin",
        ["kotlin", "test", "JUnit", "kotlin.test", "shouldBe", "AssertJ", "MockK", "BeforeEach"],
        "Testing",
        "Covers Kotlin testing with kotlin.test, JUnit 5, AssertJ assertions, "
        "MockK for mocking, and common test patterns.",
        "pattern",
        '''\
import kotlin.test.*
import org.junit.jupiter.api.*
import org.junit.jupiter.api.Assertions.*
import io.mockk.*
import org.assertj.core.api.Assertions.assertThat

// kotlin.test style
class SimpleTest {
    @Test
    fun `addition works`() {
        assertEquals(4, 2 + 2)
    }

    @Test
    fun `string contains`() {
        assertTrue("hello".contains("el"))
        assertFalse("hello".contains("x"))
    }
}

// JUnit 5 with AssertJ
class AssertJTest {
    @Test
    fun `assertj fluent assertions`() {
        val list = listOf(1, 2, 3)
        assertThat(list)
            .hasSize(3)
            .contains(2)
            .allMatch { it > 0 }
    }
}

// MockK
class UserService(private val repo: UserRepository) {
    fun getUser(id: Int): String = repo.findById(id) ?: "default"
}

interface UserRepository {
    fun findById(id: Int): String?
}

class MockKTest {
    @Test
    fun `mock example`() {
        val repo = mockk<UserRepository>()
        every { repo.findById(1) } returns "Alice"
        every { repo.findById(any()) } returns null

        val service = UserService(repo)
        assertEquals("Alice", service.getUser(1))
        assertEquals("default", service.getUser(99))
    }
}

// @BeforeEach / @AfterEach
class LifecycleTest {
    private var counter = 0

    @BeforeEach
    fun setup() {
        counter = 0
    }

    @Test
    fun `first test`() { counter++; assertEquals(1, counter) }

    @Test
    fun `second test`() { counter++; assertEquals(1, counter) }
}
''',
    ),
    (
        "kotlin/coroutines-channels.md",
        "kotlin",
        ["kotlin", "Channel", "produce", "consume", "BroadcastChannel", "ticker", "select"],
        "Kotlinx Coroutines Channels",
        "Shows coroutine channels: Channel basics, produce/consume, "
        "BroadcastChannel (SharedFlow), ticker, and select expression.",
        "pattern",
        '''\
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.*

fun main() = runBlocking {
    // Basic Channel (rendezvous by default)
    val channel = Channel<Int>(capacity = 2)

    launch {
        for (i in 1..5) {
            println("Sending $i")
            channel.send(i)
        }
        channel.close()
    }

    launch {
        for (value in channel) {
            println("Received $value")
            delay(50)
        }
    }

    // Produce / Consume
    val producer = produce {
        for (i in 1..3) {
            send(i * 10)
        }
    }
    producer.consumeEach { println("produced: $it") }

    // BroadcastChannel (deprecated in favor of SharedFlow)
    val shared = MutableSharedFlow<Int>(replay = 1)
    launch {
        repeat(5) { shared.emit(it) }
    }
    delay(100)

    // Ticker channel
    val ticker = ticker(100, initialDelayMillis = 0)
    launch {
        repeat(3) {
            ticker.receive()
            println("tick $it")
        }
        ticker.cancel()
    }

    // select expression
    val chan1 = Channel<String>(10)
    val chan2 = Channel<String>(10)

    launch {
        select<Unit> {
            chan1.onReceive { println("chan1: $it") }
            chan2.onReceive { println("chan2: $it") }
        }
    }

    chan1.send("from 1")
    delay(50)
    chan2.send("from 2")

    delay(200)
}
''',
    ),
    (
        "kotlin/scripting-cli.md",
        "kotlin",
        ["kotlin", "script", "kts", "kotlin-main-kts", "CLI", "args"],
        "Kotlin Scripting & CLI",
        "Shows Kotlin scripting (.kts), kotlin-main-kts dependency resolution, "
        "and command-line argument parsing patterns.",
        "pattern",
        '''\
// 1. Basic .kts script — run with: kotlin myscript.kts
// File: hello.kts
val name = args.firstOrNull() ?: "world"
println("Hello, $name!")

// 2. kotlin-main-kts with dependencies
// File: fetch.kts
//!/usr/bin/env kotlin
@file:DependsOn("com.squareup.okhttp3:okhttp:4.12.0")
@file:DependsOn("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.2")

import okhttp3.OkHttpClient
import okhttp3.Request

val client = OkHttpClient()
val request = Request.Builder()
    .url(args.firstOrNull() ?: "https://httpbin.org/get")
    .build()

client.newCall(request).execute().use { response ->
    println(response.body?.string()?.take(200))
}

// 3. Simple CLI using Kotlin main
// File: CliApp.kt
class CliApp {
    companion object {
        @JvmStatic
        fun main(args: Array<String>) {
            val options = mutableMapOf<String, String>()
            var positional = mutableListOf<String>()

            var i = 0
            while (i < args.size) {
                when {
                    args[i].startsWith("--") -> {
                        val key = args[i].removePrefix("--")
                        val value = args.getOrElse(i + 1) { "true" }
                        options[key] = value
                        i += if (value != "true") 2 else 1
                    }
                    else -> {
                        positional.add(args[i])
                        i++
                    }
                }
            }

            println("Options: $options")
            println("Positional: $positional")
        }
    }
}

// 4. Run with: kotlin -cp ... CliAppKt --name Alice --verbose file.txt
''',
    ),
]

# Quick verification
if __name__ == "__main__":
    swift_count = sum(1 for s in SNIPPETS if s[1] == "swift")
    kotlin_count = sum(1 for s in SNIPPETS if s[1] == "kotlin")
    print(f"Total entries: {len(SNIPPETS)}")
    print(f"  Swift: {swift_count}")
    print(f"  Kotlin: {kotlin_count}")

    # Validate all paths end with .md
    for path, lang, *_ in SNIPPETS:
        assert path.endswith(".md"), f"Path missing .md extension: {path}"

    print("All paths end with .md ✓")
