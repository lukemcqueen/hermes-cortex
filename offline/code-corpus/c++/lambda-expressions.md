---
language: c++
tags: [pattern, functional]
title: Lambda Expressions
description: Capture clauses [=][&][this], mutable, generic lambdas (auto), and returning lambdas from functions.
source: pattern
---

```c++
#include <iostream>
#include <vector>
#include <algorithm>
#include <functional>

int main() {
    int offset = 10;

    // --- Capture by value [=] ---
    auto add_offset = [=](int x) { return x + offset; };
    std::cout << "add_offset(5): " << add_offset(5) << "\n";

    // --- Capture by reference [&] ---
    auto increment = [&]() { offset += 5; };
    increment();
    std::cout << "offset after increment: " << offset << "\n";

    // --- Mutable lambda (capture by value, allow mutation) ---
    int counter = 0;
    auto count_up = [counter]() mutable {
        return ++counter;
    };
    std::cout << count_up() << " " << count_up() << " " << count_up() << "\n";
    std::cout << "original counter unchanged: " << counter << "\n";

    // --- Generic lambda (C++14) ---
    auto generic_add = [](auto a, auto b) { return a + b; };
    std::cout << "generic_add(3, 4): " << generic_add(3, 4) << "\n";
    std::cout << "generic_add(2.5, 1.5): " << generic_add(2.5, 1.5) << "\n";

    // --- Returning a lambda from a function ---
    auto make_multiplier = [](int factor) {
        return [factor](int x) { return x * factor; };
    };
    auto doubler = make_multiplier(2);
    auto tripler = make_multiplier(3);
    std::cout << "doubler(5): " << doubler(5) << "\n";
    std::cout << "tripler(5): " << tripler(5) << "\n";

    // --- Real-world use with STL ---
    std::vector<int> v = {1, 2, 3, 4, 5};
    std::for_each(v.begin(), v.end(), [](int& n) { n *= 2; });
    for (int x : v) std::cout << x << " ";
    std::cout << "\n";

    return 0;
}

```
