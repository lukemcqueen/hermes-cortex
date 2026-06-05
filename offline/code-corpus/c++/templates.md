---
language: c++
tags: [pattern, generics]
title: Templates
description: Function templates, class templates, template specialization, and variadic templates (C++11/17).
source: pattern
---

```c++
#include <iostream>
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
    std::cout << "\n";
}

int main() {
    // Function template
    std::cout << "max_of(3, 7): " << max_of(3, 7) << "\n";
    std::cout << "max_of(3.14, 2.71): " << max_of(3.14, 2.71) << "\n";

    // Class template
    Box<int> int_box(42);
    Box<std::string> str_box("hello");
    std::cout << "int_box: " << int_box.get() << "\n";
    std::cout << "str_box: " << str_box.get() << "\n";

    // Specialization
    Box<bool> bool_box(true);
    std::cout << "bool_box: " << bool_box.to_string() << "\n";

    // Variadic
    std::cout << "sum_all(1, 2, 3, 4): " << sum_all(1, 2, 3, 4) << "\n";
    print_all("hello", 42, 3.14);
    return 0;
}

```
