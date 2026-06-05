---
language: c++
tags: [pattern, move]
title: Move Semantics & Perfect Forwarding
description: std::move, std::forward, rvalue references (&&), move constructor, move assignment, and universal references with forwarding.
source: pattern
---

```c++
#include <iostream>
#include <string>
#include <utility>
#include <vector>

class Widget {
    std::string name_;
public:
    explicit Widget(std::string name) : name_(std::move(name)) {
        std::cout << "Widget constructed: " << name_ << "\n";
    }

    Widget(const Widget& other) : name_(other.name_) {
        std::cout << "Widget COPY: " << name_ << "\n";
    }

    Widget(Widget&& other) noexcept : name_(std::move(other.name_)) {
        std::cout << "Widget MOVE: " << name_ << "\n";
    }

    Widget& operator=(Widget&& other) noexcept {
        if (this != &other) {
            name_ = std::move(other.name_);
            std::cout << "Widget MOVE assign\n";
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
    std::cout << "\n--- Move semantics ---\n";
    Widget a(name);                // copy from name
    Widget b(std::move(a));        // move from a

    std::vector<Widget> widgets;
    widgets.reserve(2);
    std::cout << "\n--- Emplace back ---\n";
    widgets.emplace_back("temporary");  // constructs in-place

    std::cout << "\n--- Perfect forwarding ---\n";
    relay(std::string("permanent"));

    std::cout << "\n--- make_wrapper ---\n";
    auto wptr = make_wrapper<Widget>("factory");

    return 0;
}

```
