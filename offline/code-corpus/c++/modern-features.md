---
language: c++
tags: [pattern, modern]
title: C++11/14/17/20 Features
description: auto, decltype, constexpr, if constexpr, structured bindings, fold expressions, and concepts (C++20).
source: pattern
---

```c++
#include <iostream>
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
    std::cout << value << "\n";
}

int main() {
    // auto + decltype
    auto x = 42;
    decltype(x) y = 99;
    std::cout << "add(3, 4) = " << add(3, 4) << "\n";

    // constexpr
    constexpr int f10 = factorial(10);
    std::cout << "factorial(10) = " << f10 << "\n";

    constexpr int fib = fibonacci(10);
    std::cout << "fibonacci(10) = " << fib << "\n";

    // if constexpr
    std::cout << "magnitude(-5) = " << magnitude(-5) << "\n";
    std::cout << "magnitude("hello") = " << magnitude("hello") << "\n";

    // Structured bindings
    auto [name, age, weight] = get_person();
    std::cout << name << " age=" << age << " weight=" << weight << "\n";

    Point p{1.0, 2.0, 3.0};
    auto [px, py, pz] = p;
    std::cout << "point: " << px << ", " << py << ", " << pz << "\n";

    // Fold expressions
    std::cout << "sum(1, 2, 3, 4, 5) = " << sum(1, 2, 3, 4, 5) << "\n";

    // Concepts (C++20)
    std::cout << "double_it(21) = " << double_it(21) << "\n";

    return 0;
}

```
