---
language: c++
tags: [pattern, functional]
title: Function Objects & std::function
description: Functors (operator() overload), std::function for type-erased callables, std::bind, std::mem_fn, and callable concepts.
source: pattern
---

```c++
#include <iostream>
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
    std::cout << label << ": " << (a + b) << "\n";
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
    std::cout << "times3(7) = " << times3(7) << "\n";

    Counter c;
    std::cout << "Counter: " << c() << " " << c() << " " << c() << "\n";

    // Functor with STL
    std::vector<int> v = {1, 2, 3, 4, 5};
    std::transform(v.begin(), v.end(), v.begin(), Multiplier(10));
    std::cout << "After transform: ";
    for (int x : v) std::cout << x << " ";
    std::cout << "\n";

    // --- std::function ---
    std::function<int(int, int)> fn = [](int a, int b) { return a + b; };
    std::cout << "fn(3, 4) = " << fn(3, 4) << "\n";

    // Assign different callables
    fn = std::multiplies<int>();
    std::cout << "fn(3, 4) = " << fn(3, 4) << "\n";

    // std::function as parameter
    execute_twice([](int x) { std::cout << "Value: " << x << "\n"; }, 42);

    // --- std::bind ---
    auto bound = std::bind(print_sum, 10, std::placeholders::_1, "Sum");
    bound(5);   // prints "Sum: 15"
    bound(20);  // prints "Sum: 30"

    // --- std::mem_fn ---
    Calculator calc;
    auto mem_sq = std::mem_fn(&Calculator::square);
    auto mem_cu = std::mem_fn(&Calculator::cube);
    std::cout << "square(4) = " << mem_sq(calc, 4.0) << "\n";
    std::cout << "cube(3) = " << mem_cu(calc, 3.0) << "\n";

    // --- std::invoke (C++17) ---
    std::cout << "invoke: " << std::invoke(std::plus<>(), 100, 200) << "\n";

    return 0;
}

```
