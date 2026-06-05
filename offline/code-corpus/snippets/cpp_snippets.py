"""
C++ Code Snippets Module

A collection of 22 C++17/20 code snippets covering core language
features, standard library patterns, and modern C++ idioms.

Each snippet is a 7-tuple:
  (rel_path, language, tags, title, description, source, code)
"""

SNIPPETS = [
    # =========================================================================
    # 1. Classes & Inheritance
    # =========================================================================
    (
        "c++/classes-inheritance.md",
        "c++",
        ["pattern", "oop"],
        "Classes & Inheritance",
        "Class definition, access control (public/protected/private), "
        "inheritance, virtual functions, override, and final specifiers.",
        "pattern",
        """#include <iostream>
#include <memory>
#include <vector>

class Animal {
public:
    virtual ~Animal() = default;
    virtual void speak() const = 0;
};

class Dog final : public Animal {
public:
    void speak() const override { std::cout << "Woof!\\n"; }
};

class Cat final : public Animal {
public:
    void speak() const override { std::cout << "Meow!\\n"; }
};

// Protected / private inheritance example
class Base {
protected:
    int protected_val_{42};
private:
    int private_val_{0};
};

class Derived : public Base {
public:
    int get_protected() const { return protected_val_; }
    // Cannot access private_val_
};

int main() {
    std::vector<std::unique_ptr<Animal>> animals;
    animals.push_back(std::make_unique<Dog>());
    animals.push_back(std::make_unique<Cat>());
    for (const auto& a : animals) a->speak();

    Derived d;
    std::cout << "Protected value: " << d.get_protected() << "\\n";
    return 0;
}
""",
    ),

    # =========================================================================
    # 2. RAII & Destructors
    # =========================================================================
    (
        "c++/raii-destructors.md",
        "c++",
        ["pattern", "memory"],
        "RAII & Destructors",
        "Constructor/destructor, Rule of Five, move semantics, and "
        "smart pointer RAII wrappers (unique_ptr, shared_ptr, weak_ptr).",
        "pattern",
        """#include <iostream>
#include <cstring>
#include <utility>

// Rule-of-Five class: manages a dynamically allocated C-string
class StringBuffer {
    char* data_;
    std::size_t size_;

public:
    // Constructor
    explicit StringBuffer(const char* str)
        : size_(std::strlen(str))
        , data_(new char[size_ + 1])
    {
        std::strcpy(data_, str);
        std::cout << "Constructed: " << data_ << "\\n";
    }

    // Destructor
    ~StringBuffer() {
        std::cout << "Destructed: " << (data_ ? data_ : "nullptr") << "\\n";
        delete[] data_;
    }

    // Copy constructor
    StringBuffer(const StringBuffer& other)
        : size_(other.size_)
        , data_(new char[size_ + 1])
    {
        std::strcpy(data_, other.data_);
        std::cout << "Copy constructed\\n";
    }

    // Copy assignment
    StringBuffer& operator=(const StringBuffer& other) {
        if (this != &other) {
            delete[] data_;
            size_ = other.size_;
            data_ = new char[size_ + 1];
            std::strcpy(data_, other.data_);
            std::cout << "Copy assigned\\n";
        }
        return *this;
    }

    // Move constructor
    StringBuffer(StringBuffer&& other) noexcept
        : data_(other.data_)
        , size_(other.size_)
    {
        other.data_ = nullptr;
        other.size_ = 0;
        std::cout << "Move constructed\\n";
    }

    // Move assignment
    StringBuffer& operator=(StringBuffer&& other) noexcept {
        if (this != &other) {
            delete[] data_;
            data_ = other.data_;
            size_ = other.size_;
            other.data_ = nullptr;
            other.size_ = 0;
            std::cout << "Move assigned\\n";
        }
        return *this;
    }

    const char* c_str() const { return data_; }
};

int main() {
    StringBuffer a("Hello, RAII!");
    StringBuffer b = a;            // copy
    StringBuffer c = std::move(a); // move
    b = c;                         // copy assign
    b = std::move(c);              // move assign
    return 0;
}
""",
    ),

    # =========================================================================
    # 3. Templates
    # =========================================================================
    (
        "c++/templates.md",
        "c++",
        ["pattern", "generics"],
        "Templates",
        "Function templates, class templates, template specialization, "
        "and variadic templates (C++11/17).",
        "pattern",
        """#include <iostream>
#include <string>
#include <sstream>

// ----- Function template -----
template <typename T>
T max_of(T a, T b) {
    return (a > b) ? a : b;
}

// ----- Class template -----
template <typename T>
class Box {
    T value_;
public:
    explicit Box(T v) : value_(v) {}
    T get() const { return value_; }
    void set(T v) { value_ = v; }
};

// ----- Explicit specialization -----
template <>
class Box<bool> {
    bool value_;
public:
    explicit Box(bool v) : value_(v) {}
    bool get() const { return value_; }
    std::string to_string() const { return value_ ? "true" : "false"; }
};

// ----- Variadic template (C++17 fold expression) -----
template <typename... Args>
auto sum_all(Args... args) {
    return (args + ...);  // fold right
}

template <typename... Args>
void print_all(Args... args) {
    ((std::cout << args << " "), ...);  // fold over comma
    std::cout << "\\n";
}

int main() {
    // Function template
    std::cout << "max_of(3, 7): " << max_of(3, 7) << "\\n";
    std::cout << "max_of(3.14, 2.71): " << max_of(3.14, 2.71) << "\\n";

    // Class template
    Box<int> int_box(42);
    Box<std::string> str_box("hello");
    std::cout << "int_box: " << int_box.get() << "\\n";
    std::cout << "str_box: " << str_box.get() << "\\n";

    // Specialization
    Box<bool> bool_box(true);
    std::cout << "bool_box: " << bool_box.to_string() << "\\n";

    // Variadic
    std::cout << "sum_all(1, 2, 3, 4): " << sum_all(1, 2, 3, 4) << "\\n";
    print_all("hello", 42, 3.14);
    return 0;
}
""",
    ),

    # =========================================================================
    # 4. STL Containers
    # =========================================================================
    (
        "c++/stl-containers.md",
        "c++",
        ["pattern", "containers"],
        "STL Containers",
        "vector, map, unordered_map, set, array, deque — construction, "
        "iteration, insertion, lookup, and when to use each.",
        "pattern",
        """#include <iostream>
#include <vector>
#include <map>
#include <unordered_map>
#include <set>
#include <array>
#include <deque>
#include <string>

int main() {
    // --- vector: dynamic contiguous array (use by default) ---
    std::vector<int> vec = {1, 2, 3, 4, 5};
    vec.push_back(6);
    std::cout << "vector back: " << vec.back() << ", size: " << vec.size() << "\\n";

    // --- map: ordered key-value (red-black tree, O(log n)) ---
    std::map<std::string, int> ages;
    ages["Alice"] = 30;
    ages["Bob"] = 25;
    ages.insert({"Charlie", 35});
    for (const auto& [name, age] : ages)
        std::cout << name << ": " << age << "\\n";

    // --- unordered_map: hash table (O(1) average) ---
    std::unordered_map<std::string, double> prices;
    prices["apple"] = 1.20;
    prices["banana"] = 0.80;

    // --- set: ordered unique elements ---
    std::set<int> unique = {3, 1, 4, 1, 5, 9, 2, 6, 5, 3};
    for (int x : unique) std::cout << x << " ";
    std::cout << "\\n";

    // --- array: fixed-size stack array ---
    std::array<int, 4> fixed = {10, 20, 30, 40};
    std::cout << "array[2]: " << fixed[2] << "\\n";

    // --- deque: double-ended queue ---
    std::deque<int> dq = {2, 3, 4};
    dq.push_front(1);
    dq.push_back(5);
    for (int x : dq) std::cout << x << " ";
    std::cout << "\\n";

    // When to use each:
    // vector  – default; contiguous cache-friendly
    // deque   – push/pop both ends
    // map     – ordered lookups, range queries
    // unordered_map – fast hash lookups (no ordering)
    // set     – ordered unique collection
    // array   – compile-time fixed size on stack
    return 0;
}
""",
    ),

    # =========================================================================
    # 5. STL Algorithms
    # =========================================================================
    (
        "c++/stl-algorithms.md",
        "c++",
        ["pattern", "algorithms"],
        "STL Algorithms",
        "sort, find_if, accumulate, transform, copy_if, and the "
        "erase-remove idiom.",
        "pattern",
        """#include <iostream>
#include <vector>
#include <algorithm>
#include <numeric>
#include <string>

int main() {
    std::vector<int> v = {3, 1, 4, 1, 5, 9, 2, 6, 5, 3};

    // --- sort ---
    std::sort(v.begin(), v.end());
    for (int x : v) std::cout << x << " ";
    std::cout << "\\n";

    // --- find_if ---
    auto it = std::find_if(v.begin(), v.end(), [](int n) { return n > 5; });
    if (it != v.end())
        std::cout << "First >5: " << *it << "\\n";

    // --- accumulate ---
    int sum = std::accumulate(v.begin(), v.end(), 0);
    std::cout << "Sum: " << sum << "\\n";

    // --- transform ---
    std::vector<int> squares(v.size());
    std::transform(v.begin(), v.end(), squares.begin(),
                   [](int n) { return n * n; });
    for (int x : squares) std::cout << x << " ";
    std::cout << "\\n";

    // --- copy_if ---
    std::vector<int> evens;
    std::copy_if(v.begin(), v.end(), std::back_inserter(evens),
                 [](int n) { return n % 2 == 0; });
    for (int x : evens) std::cout << x << " ";
    std::cout << "\\n";

    // --- erase-remove idiom ---
    std::vector<int> w = {1, 2, 3, 2, 4, 2, 5};
    w.erase(std::remove(w.begin(), w.end(), 2), w.end());
    for (int x : w) std::cout << x << " ";
    std::cout << "\\n";

    return 0;
}
""",
    ),

    # =========================================================================
    # 6. Lambda Expressions
    # =========================================================================
    (
        "c++/lambda-expressions.md",
        "c++",
        ["pattern", "functional"],
        "Lambda Expressions",
        "Capture clauses [=][&][this], mutable, generic lambdas (auto), "
        "and returning lambdas from functions.",
        "pattern",
        """#include <iostream>
#include <vector>
#include <algorithm>
#include <functional>

int main() {
    int offset = 10;

    // --- Capture by value [=] ---
    auto add_offset = [=](int x) { return x + offset; };
    std::cout << "add_offset(5): " << add_offset(5) << "\\n";

    // --- Capture by reference [&] ---
    auto increment = [&]() { offset += 5; };
    increment();
    std::cout << "offset after increment: " << offset << "\\n";

    // --- Mutable lambda (capture by value, allow mutation) ---
    int counter = 0;
    auto count_up = [counter]() mutable {
        return ++counter;
    };
    std::cout << count_up() << " " << count_up() << " " << count_up() << "\\n";
    std::cout << "original counter unchanged: " << counter << "\\n";

    // --- Generic lambda (C++14) ---
    auto generic_add = [](auto a, auto b) { return a + b; };
    std::cout << "generic_add(3, 4): " << generic_add(3, 4) << "\\n";
    std::cout << "generic_add(2.5, 1.5): " << generic_add(2.5, 1.5) << "\\n";

    // --- Returning a lambda from a function ---
    auto make_multiplier = [](int factor) {
        return [factor](int x) { return x * factor; };
    };
    auto doubler = make_multiplier(2);
    auto tripler = make_multiplier(3);
    std::cout << "doubler(5): " << doubler(5) << "\\n";
    std::cout << "tripler(5): " << tripler(5) << "\\n";

    // --- Real-world use with STL ---
    std::vector<int> v = {1, 2, 3, 4, 5};
    std::for_each(v.begin(), v.end(), [](int& n) { n *= 2; });
    for (int x : v) std::cout << x << " ";
    std::cout << "\\n";

    return 0;
}
""",
    ),

    # =========================================================================
    # 7. Move Semantics & Perfect Forwarding
    # =========================================================================
    (
        "c++/move-semantics-forwarding.md",
        "c++",
        ["pattern", "move"],
        "Move Semantics & Perfect Forwarding",
        "std::move, std::forward, rvalue references (&&), move constructor, "
        "move assignment, and universal references with forwarding.",
        "pattern",
        """#include <iostream>
#include <string>
#include <utility>
#include <vector>

class Widget {
    std::string name_;
public:
    explicit Widget(std::string name) : name_(std::move(name)) {
        std::cout << "Widget constructed: " << name_ << "\\n";
    }

    Widget(const Widget& other) : name_(other.name_) {
        std::cout << "Widget COPY: " << name_ << "\\n";
    }

    Widget(Widget&& other) noexcept : name_(std::move(other.name_)) {
        std::cout << "Widget MOVE: " << name_ << "\\n";
    }

    Widget& operator=(Widget&& other) noexcept {
        if (this != &other) {
            name_ = std::move(other.name_);
            std::cout << "Widget MOVE assign\\n";
        }
        return *this;
    }
};

// ----- Perfect forwarding example -----
template <typename T, typename... Args>
std::unique_ptr<T> make_wrapper(Args&&... args) {
    return std::make_unique<T>(std::forward<Args>(args)...);
}

// Forwarding reference (universal reference)
template <typename T>
void relay(T&& arg) {
    // Perfect forward to a function
    Widget w(std::forward<T>(arg));
}

int main() {
    std::string name = "Hello";

    // Move semantics
    std::cout << "\\n--- Move semantics ---\\n";
    Widget a(name);                // copy from name
    Widget b(std::move(a));        // move from a

    std::vector<Widget> widgets;
    widgets.reserve(2);
    std::cout << "\\n--- Emplace back ---\\n";
    widgets.emplace_back("temporary");  // constructs in-place

    std::cout << "\\n--- Perfect forwarding ---\\n";
    relay(std::string("permanent"));

    std::cout << "\\n--- make_wrapper ---\\n";
    auto wptr = make_wrapper<Widget>("factory");

    return 0;
}
""",
    ),

    # =========================================================================
    # 8. Exception Safety
    # =========================================================================
    (
        "c++/exception-safety.md",
        "c++",
        ["pattern", "error-handling"],
        "Exception Safety",
        "try/catch, noexcept specifier, exception guarantees (basic/strong/nothrow), "
        "custom exception classes, and stack unwinding.",
        "pattern",
        """#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

// ----- Custom exception -----
class CalculationError : public std::runtime_error {
public:
    explicit CalculationError(const std::string& msg, int code = -1)
        : std::runtime_error(msg), error_code_(code) {}

    int error_code() const noexcept { return error_code_; }

private:
    int error_code_;
};

// ----- noexcept guarantees -----
// Strong guarantee: either fully succeeds or leaves state unchanged
class Account {
    double balance_ = 0.0;
public:
    explicit Account(double initial) noexcept : balance_(initial) {}

    // Strong guarantee via copy-and-swap
    void deposit(double amount) {
        if (amount < 0)
            throw CalculationError("Negative deposit", 100);
        double new_balance = balance_ + amount;
        if (new_balance < balance_ && amount > 0)
            throw std::overflow_error("Overflow detected");
        balance_ = new_balance;  // commit — only one non-throwing assignment
    }

    double balance() const noexcept { return balance_; }
};

// noexcept move constructor
class Resource {
    int* data_ = nullptr;
public:
    Resource() : data_(new int[100]) {}
    ~Resource() { delete[] data_; }

    Resource(Resource&& other) noexcept : data_(std::exchange(other.data_, nullptr)) {}
    Resource& operator=(Resource&& other) noexcept {
        if (this != &other) {
            delete[] data_;
            data_ = std::exchange(other.data_, nullptr);
        }
        return *this;
    }

    Resource(const Resource&) = delete;
    Resource& operator=(const Resource&) = delete;
};

int main() {
    // Basic try/catch
    try {
        Account acct(100.0);
        acct.deposit(50.0);
        std::cout << "Balance: " << acct.balance() << "\\n";
        acct.deposit(-10.0);  // throws
    } catch (const CalculationError& e) {
        std::cout << "Calculation error [" << e.error_code()
                  << "]: " << e.what() << "\\n";
    } catch (const std::exception& e) {
        std::cout << "Standard error: " << e.what() << "\\n";
    }

    // Stack unwinding example
    std::cout << "\\n--- Stack unwinding ---\\n";
    try {
        std::vector<int> vec(10, 42);
        std::cout << "vec[0] = " << vec[0] << "\\n";
        // vec.at(100) throws std::out_of_range
        std::cout << "vec[100] = " << vec.at(100) << "\\n";
        std::cout << "This line won't execute\\n";
    } catch (const std::out_of_range& e) {
        std::cout << "Caught: " << e.what() << "\\n";
    }
    std::cout << "Program continues after catch\\n";

    return 0;
}
""",
    ),

    # =========================================================================
    # 9. File I/O & Streams
    # =========================================================================
    (
        "c++/file-io-streams.md",
        "c++",
        ["pattern", "io"],
        "File I/O & Streams",
        "fstream/ifstream/ofstream for file I/O, stringstream for in-memory "
        "formatting, getline for line-based input, binary I/O, and stream states.",
        "pattern",
        """#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

int main() {
    // --- Writing to a file ---
    {
        std::ofstream out("example.txt");
        if (!out) {
            std::cerr << "Failed to write\\n";
            return 1;
        }
        out << "Hello, file!\\n";
        out << "Line 2: " << 42 << "\\n";
    }  // out closes automatically (RAII)

    // --- Reading line by line ---
    {
        std::ifstream in("example.txt");
        if (!in) {
            std::cerr << "Failed to read\\n";
            return 1;
        }
        std::string line;
        while (std::getline(in, line)) {
            std::cout << "Read: " << line << "\\n";
        }
    }

    // --- StringStream (in-memory parsing) ---
    {
        std::string data = "Alice 30 85.5\\nBob 25 92.3\\n";
        std::istringstream iss(data);
        std::string name;
        int age;
        double score;
        while (iss >> name >> age >> score) {
            std::cout << name << " is " << age
                      << " years old, score: " << score << "\\n";
        }
    }

    // --- Binary I/O ---
    {
        struct Record { int id; double value; };
        Record wr{1, 3.14159};

        // Write binary
        std::ofstream bout("data.bin", std::ios::binary);
        bout.write(reinterpret_cast<const char*>(&wr), sizeof(wr));
        bout.close();

        // Read binary
        Record rd;
        std::ifstream bin("data.bin", std::ios::binary);
        bin.read(reinterpret_cast<char*>(&rd), sizeof(rd));
        std::cout << "Binary read: id=" << rd.id << ", value=" << rd.value << "\\n";
    }

    // --- Stream states ---
    {
        std::ifstream f("nonexistent.txt");
        if (!f.good()) {
            std::cout << "Stream state: fail=" << f.fail()
                      << " eof=" << f.eof() << " bad=" << f.bad() << "\\n";
        }
    }

    return 0;
}
""",
    ),

    # =========================================================================
    # 10. Smart Pointers & Memory
    # =========================================================================
    (
        "c++/smart-pointers.md",
        "c++",
        ["pattern", "memory"],
        "Smart Pointers & Memory",
        "std::unique_ptr (exclusive ownership), std::shared_ptr (shared ownership), "
        "std::weak_ptr, std::make_unique, std::make_shared, aliasing, custom deleters.",
        "pattern",
        """#include <iostream>
#include <memory>
#include <string>
#include <vector>

struct Item {
    std::string name;
    explicit Item(std::string n) : name(std::move(n)) {
        std::cout << "Item created: " << name << "\\n";
    }
    ~Item() { std::cout << "Item destroyed: " << name << "\\n"; }
};

// Custom deleter
struct FileCloser {
    void operator()(FILE* f) const {
        if (f) {
            std::cout << "Closing file\\n";
            fclose(f);
        }
    }
};

int main() {
    // --- unique_ptr (exclusive ownership) ---
    std::cout << "--- unique_ptr ---\\n";
    {
        auto u1 = std::make_unique<Item>("unique1");
        // auto u2 = u1;            // error: no copy
        auto u2 = std::move(u1);    // ownership transfer
        if (!u1) std::cout << "u1 is now null\\n";
        std::cout << "u2 owns: " << u2->name << "\\n";
    }  // u2 destroyed

    // --- shared_ptr (shared ownership) ---
    std::cout << "\\n--- shared_ptr ---\\n";
    {
        auto s1 = std::make_shared<Item>("shared1");
        {
            auto s2 = s1;  // copy, refcount=2
            std::cout << "Use count: " << s1.use_count() << "\\n";
        }  // refcount=1
        std::cout << "Use count: " << s1.use_count() << "\\n";
    }  // refcount=0, destroyed

    // --- weak_ptr (non-owning observer) ---
    std::cout << "\\n--- weak_ptr ---\\n";
    std::weak_ptr<Item> wp;
    {
        auto sp = std::make_shared<Item>("temporary");
        wp = sp;
        if (auto locked = wp.lock())
            std::cout << "Locked: " << locked->name << "\\n";
    }
    if (wp.expired())
        std::cout << "weak_ptr expired\\n";

    // --- Custom deleter with unique_ptr ---
    std::cout << "\\n--- Custom deleter ---\\n";
    {
        std::unique_ptr<FILE, FileCloser> file(fopen("/dev/null", "w"));
        if (file) std::cout << "File opened\\n";
    }  // FileCloser called

    // --- vector of unique_ptr ---
    std::cout << "\\n--- vector<unique_ptr> ---\\n";
    std::vector<std::unique_ptr<Item>> items;
    items.push_back(std::make_unique<Item>("vec_item"));

    return 0;
}
""",
    ),

    # =========================================================================
    # 11. Multithreading
    # =========================================================================
    (
        "c++/multithreading.md",
        "c++",
        ["pattern", "concurrency"],
        "Multithreading",
        "std::thread, std::async, std::mutex, std::lock_guard, "
        "std::condition_variable, std::future, std::promise.",
        "pattern",
        """#include <iostream>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <future>
#include <vector>
#include <chrono>
#include <queue>

std::mutex cout_mutex;

// --- Basic thread with mutex ---
void worker(int id) {
    std::lock_guard<std::mutex> lock(cout_mutex);
    std::cout << "Worker " << id << " running on thread "
              << std::this_thread::get_id() << "\\n";
}

// --- Thread-safe queue with condition_variable ---
template <typename T>
class ThreadSafeQueue {
    std::queue<T> queue_;
    mutable std::mutex mtx_;
    std::condition_variable cv_;
public:
    void push(T value) {
        std::lock_guard<std::mutex> lock(mtx_);
        queue_.push(std::move(value));
        cv_.notify_one();
    }

    T pop() {
        std::unique_lock<std::mutex> lock(mtx_);
        cv_.wait(lock, [this] { return !queue_.empty(); });
        T value = std::move(queue_.front());
        queue_.pop();
        return value;
    }
};

// --- Async / future / promise ---
int compute_square(int x) {
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    return x * x;
}

int main() {
    // --- Basic threads ---
    std::cout << "--- Basic threads ---\\n";
    std::vector<std::thread> threads;
    for (int i = 0; i < 4; ++i)
        threads.emplace_back(worker, i);
    for (auto& t : threads) t.join();

    // --- Thread-safe queue with condition variable ---
    std::cout << "\\n--- Thread-safe queue ---\\n";
    ThreadSafeQueue<int> tsq;
    std::thread producer([&] {
        for (int i = 0; i < 5; ++i) {
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
            tsq.push(i);
        }
    });
    std::thread consumer([&] {
        for (int i = 0; i < 5; ++i) {
            int val = tsq.pop();
            std::lock_guard<std::mutex> lock(cout_mutex);
            std::cout << "Consumed: " << val << "\\n";
        }
    });
    producer.join();
    consumer.join();

    // --- Async + future ---
    std::cout << "\\n--- Async / future ---\\n";
    std::vector<std::future<int>> futures;
    for (int i = 1; i <= 4; ++i)
        futures.push_back(std::async(std::launch::async, compute_square, i));
    for (auto& f : futures)
        std::cout << "Result: " << f.get() << "\\n";

    return 0;
}
""",
    ),

    # =========================================================================
    # 12. C++11/14/17/20 Features
    # =========================================================================
    (
        "c++/modern-features.md",
        "c++",
        ["pattern", "modern"],
        "C++11/14/17/20 Features",
        "auto, decltype, constexpr, if constexpr, structured bindings, "
        "fold expressions, and concepts (C++20).",
        "pattern",
        """#include <iostream>
#include <tuple>
#include <type_traits>
#include <concepts>
#include <string>
#include <vector>

// ----- C++11: auto & decltype -----
auto add(int a, int b) -> decltype(a + b) { return a + b; }

// ----- C++11/14: constexpr -----
constexpr int factorial(int n) {
    return (n <= 1) ? 1 : n * factorial(n - 1);
}

// C++14 constexpr can have local variables and loops
constexpr int fibonacci(int n) {
    int a = 0, b = 1;
    for (int i = 0; i < n; ++i) {
        int next = a + b;
        a = b;
        b = next;
    }
    return a;
}

// ----- C++17: if constexpr -----
template <typename T>
auto magnitude(T value) {
    if constexpr (std::is_arithmetic_v<T>) {
        return value < 0 ? -value : value;
    } else {
        return value;
    }
}

// ----- C++17: Structured bindings -----
struct Point { double x, y, z; };
std::tuple<std::string, int, double> get_person() {
    return {"Alice", 30, 65.5};
}

// ----- C++17: Fold expressions -----
template <typename... Args>
auto sum(Args... args) {
    return (args + ...);
}

// ----- C++20: Concepts -----
template <std::integral T>
T double_it(T value) {
    return value * 2;
}

// Custom concept
template <typename T>
concept Printable = requires(T t) {
    std::cout << t;
};

void print_printable(Printable auto const& value) {
    std::cout << value << "\\n";
}

int main() {
    // auto + decltype
    auto x = 42;
    decltype(x) y = 99;
    std::cout << "add(3, 4) = " << add(3, 4) << "\\n";

    // constexpr
    constexpr int f10 = factorial(10);
    std::cout << "factorial(10) = " << f10 << "\\n";

    constexpr int fib = fibonacci(10);
    std::cout << "fibonacci(10) = " << fib << "\\n";

    // if constexpr
    std::cout << "magnitude(-5) = " << magnitude(-5) << "\\n";
    std::cout << "magnitude(\"hello\") = " << magnitude("hello") << "\\n";

    // Structured bindings
    auto [name, age, weight] = get_person();
    std::cout << name << " age=" << age << " weight=" << weight << "\\n";

    Point p{1.0, 2.0, 3.0};
    auto [px, py, pz] = p;
    std::cout << "point: " << px << ", " << py << ", " << pz << "\\n";

    // Fold expressions
    std::cout << "sum(1, 2, 3, 4, 5) = " << sum(1, 2, 3, 4, 5) << "\\n";

    // Concepts (C++20)
    std::cout << "double_it(21) = " << double_it(21) << "\\n";

    return 0;
}
""",
    ),

    # =========================================================================
    # 13. Strings & String Views
    # =========================================================================
    (
        "c++/strings-stringview.md",
        "c++",
        ["pattern", "strings"],
        "Strings & String Views",
        "std::string manipulation (find, replace, substr, append), "
        "std::string_view (C++17) for non-owning string references, "
        "to/from number conversions (std::to_string, stoi/stod).",
        "pattern",
        """#include <iostream>
#include <string>
#include <string_view>
#include <vector>
#include <charconv>  // std::from_chars (C++17)

int main() {
    // --- String construction & manipulation ---
    std::string s = "Hello, C++ World!";
    std::cout << "length: " << s.length() << "\\n";

    // Find / replace / substr
    auto pos = s.find("C++");
    if (pos != std::string::npos)
        std::cout << "Found 'C++' at position " << pos << "\\n";

    std::string sub = s.substr(7, 3);  // "C++"
    std::cout << "substr: '" << sub << "'\\n";

    s.replace(pos, 3, "C++17");
    std::cout << "after replace: " << s << "\\n";

    s.append(" is great!");
    std::cout << "after append: " << s << "\\n";

    // --- String to/from number conversions ---
    // to_string
    std::string num_str = std::to_string(42);
    std::cout << "to_string(42): " << num_str << "\\n";

    // stoi / stod / stoll
    std::string int_val = "1234";
    std::string dbl_val = "3.14159";
    int i = std::stoi(int_val);
    double d = std::stod(dbl_val);
    std::cout << "stoi: " << i << ", stod: " << d << "\\n";

    // C++17 from_chars (no allocation, no exceptions)
    std::string number = "2024";
    int parsed = 0;
    auto [ptr, ec] = std::from_chars(number.data(),
                                     number.data() + number.size(), parsed);
    if (ec == std::errc{})
        std::cout << "from_chars: " << parsed << "\\n";

    // --- string_view (C++17, non-owning) ---
    std::cout << "\\n--- string_view ---\\n";
    const char* raw = "This is a C-string";
    std::string_view sv(raw);  // no copy
    std::cout << "string_view: " << sv << "\\n";
    std::cout << "first 4 chars: " << sv.substr(0, 4) << "\\n";

    // Efficient splitting with string_view
    std::string_view csv = "apple,banana,cherry,date";
    std::vector<std::string_view> parts;
    size_t start = 0;
    while (start < csv.size()) {
        auto comma = csv.find(',', start);
        if (comma == std::string_view::npos) comma = csv.size();
        parts.push_back(csv.substr(start, comma - start));
        start = comma + 1;
    }
    for (auto part : parts)
        std::cout << "  part: '" << part << "'\\n";

    return 0;
}
""",
    ),

    # =========================================================================
    # 14. Chrono & Timing
    # =========================================================================
    (
        "c++/chrono-timing.md",
        "c++",
        ["pattern", "time"],
        "Chrono & Timing",
        "std::chrono::duration, time_point, high_resolution_clock, "
        "system_clock::now, sleep_for, and measuring elapsed time.",
        "pattern",
        """#include <iostream>
#include <chrono>
#include <thread>
#include <string>
#include <format>   // C++20, or use fmtlib

using namespace std::chrono_literals;

int main() {
    // --- Duration literals ---
    auto ms = 500ms;
    auto sec = 2s;
    auto min = 1min;
    std::cout << "500ms = " << ms.count() << " ms\\n";
    std::cout << "2s = " << sec.count() << " s\\n";

    // --- Timing a function with high_resolution_clock ---
    auto start = std::chrono::high_resolution_clock::now();

    std::this_thread::sleep_for(250ms);  // simulate work

    auto end = std::chrono::high_resolution_clock::now();
    auto elapsed = std::chrono::duration_cast<std::chrono::microseconds>(end - start);

    std::cout << "Elapsed: " << elapsed.count() << " us"
              << " (" << elapsed.count() / 1000.0 << " ms)\\n";

    // --- Converting to/from time_t (system_clock) ---
    auto now = std::chrono::system_clock::now();
    std::time_t tt = std::chrono::system_clock::to_time_t(now);
    std::cout << "Current time: " << std::ctime(&tt);

    // --- Measuring with different units ---
    auto t1 = std::chrono::steady_clock::now();
    std::this_thread::sleep_for(100ms);
    auto t2 = std::chrono::steady_clock::now();

    // Duration arithmetic
    auto diff = t2 - t1;
    std::cout << "diff in ns:  " << diff.count() << "\\n";
    std::cout << "diff in ms:  "
              << std::chrono::duration_cast<std::chrono::milliseconds>(diff).count()
              << "\\n";
    std::cout << "diff in s:   "
              << std::chrono::duration_cast<std::chrono::seconds>(diff).count()
              << "\\n";

    // --- Timepoints and duration math ---
    auto later = now + 1h + 30min;  // 1.5 hours from now
    std::time_t later_tt = std::chrono::system_clock::to_time_t(later);
    std::cout << "1.5h from now: " << std::ctime(&later_tt);

    // --- C++20 chrono::parse / formatting ---
    // Uncomment if using C++20:
    // auto tp = std::chrono::system_clock::now();
    // std::cout << std::format("{:%Y-%m-%d %H:%M:%S}", tp) << "\\n";

    return 0;
}
""",
    ),

    # =========================================================================
    # 15. Enums & Type Safety
    # =========================================================================
    (
        "c++/enums-type-safety.md",
        "c++",
        ["pattern", "types"],
        "Enums & Type Safety",
        "enum class (scoped enums), underlying type specification, "
        "switch exhaustiveness, and conversion to/from integral types.",
        "pattern",
        """#include <iostream>
#include <type_traits>

// --- Scoped enum (enum class) ---
enum class Color : int {
    Red = 0,
    Green = 1,
    Blue = 2,
    Yellow = 3
};

// Implicit conversion is NOT allowed — type-safe!
// int x = Color::Red;  // ERROR

// Explicit conversion
constexpr auto to_integral(Color c) {
    return static_cast<std::underlying_type_t<Color>>(c);
}

// String representation
constexpr const char* to_string(Color c) {
    switch (c) {
        case Color::Red:    return "Red";
        case Color::Green:  return "Green";
        case Color::Blue:   return "Blue";
        case Color::Yellow: return "Yellow";
    }
    // GCC/Clang warn if not exhaustive (with -Wswitch)
    return "Unknown";
}

// --- Enum with explicit underlying type ---
enum class Permission : unsigned char {
    None    = 0b000,
    Read    = 0b001,
    Write   = 0b010,
    Execute = 0b100
};

// Bitwise operators for flag enums
constexpr Permission operator|(Permission a, Permission b) {
    return static_cast<Permission>(
        static_cast<unsigned char>(a) | static_cast<unsigned char>(b)
    );
}

constexpr bool has_flag(Permission p, Permission flag) {
    return (static_cast<unsigned char>(p) & static_cast<unsigned char>(flag)) != 0;
}

// --- Unscoped enum (legacy, avoid in modern code) ---
// enum Old { A, B, C };  // pollutes namespace

int main() {
    Color c = Color::Blue;

    // Type safety prevents implicit int conversion
    std::cout << "Color: " << to_string(c) << "\\n";
    std::cout << "As int: " << to_integral(c) << "\\n";

    // Switch exhaustiveness
    switch (c) {
        case Color::Red:    std::cout << "Red\\n"; break;
        case Color::Green:  std::cout << "Green\\n"; break;
        case Color::Blue:   std::cout << "Blue\\n"; break;
        case Color::Yellow: std::cout << "Yellow\\n"; break;
    }

    // Flags
    Permission perms = Permission::Read | Permission::Write;
    std::cout << "Can read?  " << has_flag(perms, Permission::Read) << "\\n";
    std::cout << "Can exec?  " << has_flag(perms, Permission::Execute) << "\\n";

    // Iteration workaround
    std::cout << "\\nAll colors:\\n";
    for (int i = 0; i <= 3; ++i) {
        Color col = static_cast<Color>(i);
        std::cout << "  " << to_string(col) << " (" << to_integral(col) << ")\\n";
    }

    return 0;
}
""",
    ),

    # =========================================================================
    # 16. Random
    # =========================================================================
    (
        "c++/random.md",
        "c++",
        ["pattern", "random"],
        "Random Number Generation",
        "std::random_device (true randomness source), std::mt19937 "
        "(Mersenne Twister engine), uniform_int_distribution, "
        "normal_distribution, bernoulli_distribution.",
        "pattern",
        """#include <iostream>
#include <random>
#include <vector>
#include <algorithm>
#include <iomanip>

int main() {
    // --- Seed with true random (or fall back to deterministic) ---
    std::random_device rd;
    std::mt19937 gen(rd());  // Mersenne Twister

    // --- Uniform integer distribution ---
    std::uniform_int_distribution<int> die(1, 6);
    std::cout << "10 dice rolls: ";
    for (int i = 0; i < 10; ++i)
        std::cout << die(gen) << " ";
    std::cout << "\\n";

    // --- Uniform real distribution ---
    std::uniform_real_distribution<double> uniform(0.0, 1.0);
    std::cout << "5 uniform reals: ";
    for (int i = 0; i < 5; ++i)
        std::cout << std::fixed << std::setprecision(4)
                  << uniform(gen) << " ";
    std::cout << "\\n";

    // --- Normal (Gaussian) distribution ---
    std::normal_distribution<double> normal(50.0, 15.0);  // mean=50, stddev=15
    std::vector<int> histogram(100, 0);
    for (int i = 0; i < 10000; ++i) {
        double val = normal(gen);
        int bin = static_cast<int>(val);
        if (bin >= 0 && bin < 100) ++histogram[bin];
    }

    // Print a simple histogram
    std::cout << "\\nNormal distribution histogram (mean=50, stddev=15):\\n";
    for (int i = 15; i <= 85; ++i) {
        if (histogram[i] > 0) {
            std::cout << std::setw(3) << i << ": "
                      << std::string(histogram[i] / 100, '*') << "\\n";
        }
    }

    // --- Bernoulli distribution (coin flip) ---
    std::bernoulli_distribution coin(0.7);  // 70% heads
    int heads = 0, tails = 0;
    for (int i = 0; i < 1000; ++i) {
        if (coin(gen)) ++heads;
        else ++tails;
    }
    std::cout << "\\n1000 coin flips (p=0.7): heads=" << heads
              << " tails=" << tails << "\\n";

    // --- Shuffle using random engine ---
    std::vector<int> cards(52);
    std::iota(cards.begin(), cards.end(), 1);
    std::shuffle(cards.begin(), cards.end(), gen);
    std::cout << "\\nFirst 5 shuffled cards: ";
    for (int i = 0; i < 5; ++i)
        std::cout << cards[i] << " ";
    std::cout << "\\n";

    return 0;
}
""",
    ),

    # =========================================================================
    # 17. Function Objects & std::function
    # =========================================================================
    (
        "c++/function-objects.md",
        "c++",
        ["pattern", "functional"],
        "Function Objects & std::function",
        "Functors (operator() overload), std::function for type-erased "
        "callables, std::bind, std::mem_fn, and callable concepts.",
        "pattern",
        """#include <iostream>
#include <functional>
#include <vector>
#include <algorithm>
#include <string>
#include <cmath>

// --- Functor (function object) ---
struct Multiplier {
    int factor;
    explicit Multiplier(int f) : factor(f) {}

    int operator()(int x) const {
        return x * factor;
    }
};

// --- Functor with state ---
struct Counter {
    int count = 0;
    int operator()() { return ++count; }
};

// --- std::function (type-erased callable) ---
void execute_twice(const std::function<void(int)>& fn, int val) {
    fn(val);
    fn(val);
}

// --- std::bind example ---
void print_sum(int a, int b, const std::string& label) {
    std::cout << label << ": " << (a + b) << "\\n";
}

// --- Class for mem_fn ---
class Calculator {
public:
    double square(double x) const { return x * x; }
    double cube(double x) const   { return x * x * x; }
};

int main() {
    // --- Functors ---
    Multiplier times3(3);
    std::cout << "times3(7) = " << times3(7) << "\\n";

    Counter c;
    std::cout << "Counter: " << c() << " " << c() << " " << c() << "\\n";

    // Functor with STL
    std::vector<int> v = {1, 2, 3, 4, 5};
    std::transform(v.begin(), v.end(), v.begin(), Multiplier(10));
    std::cout << "After transform: ";
    for (int x : v) std::cout << x << " ";
    std::cout << "\\n";

    // --- std::function ---
    std::function<int(int, int)> fn = [](int a, int b) { return a + b; };
    std::cout << "fn(3, 4) = " << fn(3, 4) << "\\n";

    // Assign different callables
    fn = std::multiplies<int>();
    std::cout << "fn(3, 4) = " << fn(3, 4) << "\\n";

    // std::function as parameter
    execute_twice([](int x) { std::cout << "Value: " << x << "\\n"; }, 42);

    // --- std::bind ---
    auto bound = std::bind(print_sum, 10, std::placeholders::_1, "Sum");
    bound(5);   // prints "Sum: 15"
    bound(20);  // prints "Sum: 30"

    // --- std::mem_fn ---
    Calculator calc;
    auto mem_sq = std::mem_fn(&Calculator::square);
    auto mem_cu = std::mem_fn(&Calculator::cube);
    std::cout << "square(4) = " << mem_sq(calc, 4.0) << "\\n";
    std::cout << "cube(3) = " << mem_cu(calc, 3.0) << "\\n";

    // --- std::invoke (C++17) ---
    std::cout << "invoke: " << std::invoke(std::plus<>(), 100, 200) << "\\n";

    return 0;
}
""",
    ),

    # =========================================================================
    # 18. Serialization
    # =========================================================================
    (
        "c++/serialization.md",
        "c++",
        ["pattern", "serialization"],
        "Serialization",
        "JSON serialization with nlohmann/json (single-header), "
        "binary serialization using stringstream, and protobuf notes.",
        "pattern",
        """#include <iostream>
#include <sstream>
#include <vector>
#include <string>
#include <cstdint>

// --- Binary serialization with stringstream ---
struct Player {
    std::string name;
    int level;
    double health;
    std::vector<int> inventory_ids;

    // Serialize to binary
    void serialize(std::ostream& os) const {
        size_t name_len = name.size();
        os.write(reinterpret_cast<const char*>(&name_len), sizeof(name_len));
        os.write(name.data(), name_len);
        os.write(reinterpret_cast<const char*>(&level), sizeof(level));
        os.write(reinterpret_cast<const char*>(&health), sizeof(health));
        size_t inv_size = inventory_ids.size();
        os.write(reinterpret_cast<const char*>(&inv_size), sizeof(inv_size));
        os.write(reinterpret_cast<const char*>(inventory_ids.data()),
                 inv_size * sizeof(int));
    }

    // Deserialize from binary
    void deserialize(std::istream& is) {
        size_t name_len;
        is.read(reinterpret_cast<char*>(&name_len), sizeof(name_len));
        name.resize(name_len);
        is.read(name.data(), name_len);
        is.read(reinterpret_cast<char*>(&level), sizeof(level));
        is.read(reinterpret_cast<char*>(&health), sizeof(health));
        size_t inv_size;
        is.read(reinterpret_cast<char*>(&inv_size), sizeof(inv_size));
        inventory_ids.resize(inv_size);
        is.read(reinterpret_cast<char*>(inventory_ids.data()),
                inv_size * sizeof(int));
    }
};

// --- Simple JSON-like builder (minimal, no external lib) ---
class SimpleJSON {
    std::ostringstream out_;
    bool first_ = true;
public:
    SimpleJSON& begin_object() {
        out_ << "{";
        first_ = true;
        return *this;
    }
    SimpleJSON& key(const std::string& k) {
        if (!first_) out_ << ",";
        out_ << "\\"" << k << "\\":";
        first_ = false;
        return *this;
    }
    SimpleJSON& value(const std::string& v) {
        out_ << "\\"" << v << "\\"";
        return *this;
    }
    SimpleJSON& value(int v) {
        out_ << v;
        return *this;
    }
    SimpleJSON& value(double v) {
        out_ << v;
        return *this;
    }
    SimpleJSON& end_object() {
        out_ << "}";
        return *this;
    }
    std::string str() const { return out_.str(); }
};

int main() {
    // --- Binary serialization ---
    Player p1{"Hero", 42, 95.5, {101, 202, 303}};
    std::stringstream buf;
    p1.serialize(buf);

    Player p2;
    p2.deserialize(buf);
    std::cout << "Deserialized: name=" << p2.name
              << " level=" << p2.level
              << " health=" << p2.health
              << " inventory=[";
    for (size_t i = 0; i < p2.inventory_ids.size(); ++i) {
        if (i) std::cout << ",";
        std::cout << p2.inventory_ids[i];
    }
    std::cout << "]\\n";

    // --- Simple JSON ---
    SimpleJSON json;
    json.begin_object()
        .key("name").value("Hero")
        .key("level").value(42)
        .key("health").value(95.5)
        .key("alive").value("true")
        .end_object();
    std::cout << "JSON: " << json.str() << "\\n";

    // --- Notes on nlohmann/json (single header) ---
    // #include <nlohmann/json.hpp>
    // using json = nlohmann::json;
    // json j = {{"name", "Hero"}, {"level", 42}};
    // auto name = j["name"].get<std::string>();
    //
    // --- Notes on protobuf ---
    // message Player {
    //   string name = 1;
    //   int32  level = 2;
    //   double health = 3;
    //   repeated int32 inventory_ids = 4;
    // }
    // Player p;
    // p.set_name("Hero");
    // p.SerializeToOstream(&output);
    // p.ParseFromIstream(&input);

    return 0;
}
""",
    ),

    # =========================================================================
    # 19. Type Traits & SFINAE
    # =========================================================================
    (
        "c++/type-traits-sfinae.md",
        "c++",
        ["pattern", "metaprogramming"],
        "Type Traits & SFINAE",
        "std::is_integral, std::is_floating_point, std::enable_if, "
        "std::conditional, std::void_t, and C++20 concepts requires clause.",
        "pattern",
        """#include <iostream>
#include <type_traits>
#include <concepts>
#include <string>

// ===== SFINAE (C++11/17) =====

// --- enable_if on return type ---
template <typename T>
std::enable_if_t<std::is_integral_v<T>, T>
twice(T value) {
    return value * 2;
}

template <typename T>
std::enable_if_t<std::is_floating_point_v<T>, T>
twice(T value) {
    return value * 2.0;
}

// --- enable_if on template parameter ---
template <typename T, std::enable_if_t<std::is_arithmetic_v<T>, int> = 0>
T add_ten(T value) {
    return value + 10;
}

// --- void_t for detecting member presence (C++17) ---
template <typename, typename = void>
struct has_value_type : std::false_type {};

template <typename T>
struct has_value_type<T, std::void_t<typename T::value_type>>
    : std::true_type {};

// ===== C++20 Concepts =====

// Simple concept
template <typename T>
concept Integer = std::is_integral_v<T>;

template <typename T>
concept SignedInteger = Integer<T> && std::is_signed_v<T>;

// Requires clause with compound requirement
template <typename T>
concept Incrementable = requires(T x) {
    ++x;
    x++;
    { x + x } -> std::convertible_to<T>;
};

// ===== std::conditional =====
// Compile-time type selection
template <bool UseFloat>
using PrecisionType = std::conditional_t<UseFloat, float, double>;

int main() {
    // --- SFINAE ---
    std::cout << "twice(21): " << twice(21) << "\\n";
    std::cout << "twice(3.14): " << twice(3.14) << "\\n";
    std::cout << "add_ten(100): " << add_ten(100) << "\\n";

    // --- void_t detection ---
    std::cout << "std::vector has value_type? "
              << has_value_type<std::vector<int>>::value << "\\n";
    std::cout << "int has value_type? "
              << has_value_type<int>::value << "\\n";

    // --- std::conditional ---
    PrecisionType<true> float_val = 3.14f;  // float
    PrecisionType<false> double_val = 3.1415926535;  // double
    std::cout << "float precision: " << float_val << "\\n";
    std::cout << "double precision: " << double_val << "\\n";

    // --- C++20 concepts ---
    static_assert(Integer<int>);
    static_assert(!Integer<std::string>);
    static_assert(SignedInteger<int>);
    static_assert(!SignedInteger<unsigned int>);
    static_assert(Incrementable<int>);

    auto constrained_fn = []<Integer T>(T a, T b) {
        return a + b;
    };
    std::cout << "constrained_fn(3, 4): " << constrained_fn(3, 4) << "\\n";

    return 0;
}
""",
    ),

    # =========================================================================
    # 20. Ranges & Views (C++20)
    # =========================================================================
    (
        "c++/ranges-views.md",
        "c++",
        ["pattern", "ranges"],
        "Ranges & Views (C++20)",
        "std::ranges algorithms, std::views::filter/transform/take/drop, "
        "pipe syntax (|), lazy evaluation, and range adaptors.",
        "pattern",
        """#include <iostream>
#include <ranges>
#include <vector>
#include <algorithm>
#include <numeric>
#include <string>

int main() {
    // --- Basic range operations ---
    std::vector<int> numbers = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};

    // Filter: keep even numbers, Transform: square them
    auto result = numbers
        | std::views::filter([](int n) { return n % 2 == 0; })
        | std::views::transform([](int n) { return n * n; });

    std::cout << "Even squares: ";
    for (int x : result) std::cout << x << " ";
    std::cout << "\\n";

    // --- take / drop ---
    auto first_three = numbers | std::views::take(3);
    std::cout << "First 3: ";
    for (int x : first_three) std::cout << x << " ";
    std::cout << "\\n";

    auto after_five = numbers | std::views::drop(5);
    std::cout << "After 5: ";
    for (int x : after_five) std::cout << x << " ";
    std::cout << "\\n";

    // --- Combining adaptors ---
    auto pipeline = numbers
        | std::views::filter([](int n) { return n > 3; })
        | std::views::transform([](int n) { return n * 10; })
        | std::views::take(4);

    std::cout << "Pipeline (>3 *10 take4): ";
    for (int x : pipeline) std::cout << x << " ";
    std::cout << "\\n";

    // --- Lazy evaluation ---
    // Nothing is computed until we iterate
    auto lazy = numbers
        | std::views::transform([](int n) {
              std::cout << "  computing " << n << "\\n";
              return n * 2;
          });
    std::cout << "Lazy -- not computed yet\\n";
    for (int x : lazy | std::views::take(3))
        std::cout << "Got: " << x << "\\n";

    // --- std::ranges algorithms ---
    std::vector<int> v = {5, 2, 8, 1, 9, 3, 7, 4, 6};
    std::ranges::sort(v);
    std::cout << "Sorted: ";
    for (int x : v) std::cout << x << " ";
    std::cout << "\\n";

    auto it = std::ranges::find_if(v, [](int n) { return n > 5; });
    if (it != v.end())
        std::cout << "First >5: " << *it << "\\n";

    // --- Views on a string ---
    std::string text = "Hello, World!";
    auto upper = text
        | std::views::transform([](char c) -> char {
              return static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
          });
    std::cout << "Uppercase: ";
    for (char c : upper) std::cout << c;
    std::cout << "\\n";

    // --- Zip (C++23) ---
    // auto zipped = std::views::zip(v, numbers);
    // for (auto [a, b] : zipped)
    //     std::cout << a << " -> " << b << "\\n";

    return 0;
}
""",
    ),

    # =========================================================================
    # 21. Networking (Boost.Asio basics)
    # =========================================================================
    (
        "c++/networking.md",
        "c++",
        ["pattern", "networking"],
        "Networking (Boost.Asio / C++20 std::net)",
        "Boost.Asio basics: async TCP echo server/client, steady_timer, "
        "and error_code handling. Notes on C++23 std::net.",
        "pattern",
        """// Requires: Boost.Asio (libboost-dev) or standalone Asio
// Compile: g++ -std=c++20 -I/usr/include networking.cpp -lboost_system -lpthread
//
// If using standalone Asio: #define ASIO_STANDALONE
// If using C++23 std::net (experimental): #include <experimental/net>

#include <iostream>
#include <thread>
#include <string>

// --- Boost.Asio includes ---
#include <boost/asio.hpp>

using boost::asio::ip::tcp;

// ===================== ECHO SERVER =====================
// Session handler — runs in one thread per connection
class Session : public std::enable_shared_from_this<Session> {
    tcp::socket socket_;
    enum { max_length = 1024 };
    char data_[max_length];

public:
    explicit Session(tcp::socket socket)
        : socket_(std::move(socket)) {}

    void start() { do_read(); }

private:
    void do_read() {
        auto self = shared_from_this();
        socket_.async_read_some(
            boost::asio::buffer(data_, max_length),
            [this, self](boost::system::error_code ec, std::size_t length) {
                if (!ec) {
                    do_write(length);
                }
            });
    }

    void do_write(std::size_t length) {
        auto self = shared_from_this();
        boost::asio::async_write(
            socket_,
            boost::asio::buffer(data_, length),
            [this, self](boost::system::error_code ec, std::size_t /*length*/) {
                if (!ec) {
                    do_read();  // continue reading
                }
            });
    }
};

class Server {
    tcp::acceptor acceptor_;

public:
    Server(boost::asio::io_context& io, short port)
        : acceptor_(io, tcp::endpoint(tcp::v4(), port)) {
        do_accept();
        std::cout << "Echo server listening on port " << port << "\\n";
    }

private:
    void do_accept() {
        acceptor_.async_accept(
            [this](boost::system::error_code ec, tcp::socket socket) {
                if (!ec) {
                    std::make_shared<Session>(std::move(socket))->start();
                }
                do_accept();  // accept next connection
            });
    }
};

// ===================== ECHO CLIENT =====================
void run_client(const std::string& host, short port) {
    try {
        boost::asio::io_context io;
        tcp::socket socket(io);
        tcp::resolver resolver(io);
        boost::asio::connect(socket, resolver.resolve(host, std::to_string(port)));

        std::string message = "Hello, Asio!";
        boost::asio::write(socket, boost::asio::buffer(message));

        char reply[1024];
        std::size_t len = socket.read_some(boost::asio::buffer(reply));
        std::cout << "Server echoed: " << std::string(reply, len) << "\\n";

        socket.close();
    } catch (std::exception& e) {
        std::cerr << "Client error: " << e.what() << "\\n";
    }
}

// ===================== TIMER EXAMPLE =====================
void timer_example(boost::asio::io_context& io) {
    auto timer = std::make_shared<boost::asio::steady_timer>(io);
    timer->expires_after(std::chrono::seconds(1));

    timer->async_wait([timer](boost::system::error_code ec) {
        if (!ec) {
            std::cout << "Timer fired after 1 second\\n";
        }
    });
}

int main() {
    try {
        boost::asio::io_context io;

        Server server(io, 12345);

        // Start timer
        timer_example(io);

        // Run client in a separate thread
        std::thread client_thread([&] {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            run_client("127.0.0.1", 12345);
        });

        // Run the I/O context (event loop)
        io.run();

        client_thread.join();
    } catch (std::exception& e) {
        std::cerr << "Fatal: " << e.what() << "\\n";
        return 1;
    }

    return 0;
}
""",
    ),

    # =========================================================================
    # 22. Compile-Time Programming
    # =========================================================================
    (
        "c++/compile-time-programming.md",
        "c++",
        ["pattern", "metaprogramming"],
        "Compile-Time Programming",
        "constexpr functions, consteval (C++20), constinit (C++20), "
        "static_assert, template metaprogramming basics (compile-time "
        "factorial, prime check, type lists).",
        "pattern",
        """#include <iostream>
#include <type_traits>

// ===== constexpr functions (C++11/14/17) =====

// C++11: single return statement
constexpr int factorial_c11(int n) {
    return (n <= 1) ? 1 : n * factorial_c11(n - 1);
}

// C++14: multiple statements, loops
constexpr int fibonacci(int n) {
    int a = 0, b = 1;
    for (int i = 0; i < n; ++i) {
        int next = a + b;
        a = b;
        b = next;
    }
    return a;
}

constexpr bool is_prime(int n) {
    if (n < 2) return false;
    for (int i = 2; i * i <= n; ++i)
        if (n % i == 0) return false;
    return true;
}

// ===== consteval (C++20): guaranteed compile-time evaluation =====
consteval int square(int n) { return n * n; }

// ===== constinit (C++20): guarantee static init order =====
constinit int global_value = 42;

// ===== static_assert =====
static_assert(factorial_c11(5) == 120, "5! should be 120");
static_assert(fibonacci(10) == 55, "fib(10) should be 55");
static_assert(is_prime(17), "17 is prime");
static_assert(!is_prime(1), "1 is not prime");

// ===== Template Metaprogramming basics =====

// Compile-time factorial via template recursion
template <unsigned int N>
struct Factorial {
    static constexpr unsigned int value = N * Factorial<N - 1>::value;
};

template <>
struct Factorial<0> {
    static constexpr unsigned int value = 1;
};

// Compile-time sqrt via binary search
template <unsigned int N, unsigned int Low, unsigned int High>
struct SqrtImpl {
    static constexpr unsigned int mid = (Low + High + 1) / 2;
    using next = std::conditional_t<
        (mid * mid <= N),
        SqrtImpl<N, mid, High>,
        SqrtImpl<N, Low, mid - 1>
    >;
    static constexpr unsigned int value = next::value;
};

template <unsigned int N>
struct Sqrt : SqrtImpl<N, 0, N> {};

// Base case: low == high
template <unsigned int N, unsigned int V>
struct SqrtImpl<N, V, V> {
    static constexpr unsigned int value = V;
};

// ===== Compile-time type list (basic TMP) =====
template <typename... Ts>
struct TypeList {
    static constexpr std::size_t size = sizeof...(Ts);
};

template <typename List>
struct Length;

template <typename... Ts>
struct Length<TypeList<Ts...>> {
    static constexpr std::size_t value = sizeof...(Ts);
};

int main() {
    // constexpr evaluation at compile time
    constexpr int f10 = factorial_c11(10);
    std::cout << "factorial(10) = " << f10 << "\\n";

    constexpr auto fib10 = fibonacci(10);
    std::cout << "fibonacci(10) = " << fib10 << "\\n";

    constexpr bool p17 = is_prime(17);
    std::cout << "is_prime(17) = " << p17 << "\\n";

    // consteval
    constexpr int s5 = square(5);
    std::cout << "square(5) = " << s5 << "\\n";

    // constinit
    std::cout << "global_value = " << global_value << "\\n";

    // Template metaprogramming results
    std::cout << "Factorial<6>::value = " << Factorial<6>::value << "\\n";
    std::cout << "Sqrt<144>::value = " << Sqrt<144>::value << "\\n";
    std::cout << "Sqrt<1000>::value = " << Sqrt<1000>::value << "\\n";

    // Type list
    using Types = TypeList<int, double, char, float>;
    std::cout << "TypeList size = " << Length<Types>::value << "\\n";

    // Run-time check of compile-time constants
    constexpr int computed = [] {
        int sum = 0;
        for (int i = 1; i <= 10; ++i)
            if (is_prime(i)) sum += i;
        return sum;
    }();  // IIFE lambda, evaluated at compile time
    std::cout << "Sum of primes <= 10: " << computed << "\\n";

    return 0;
}
""",
    ),
]
