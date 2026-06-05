---
language: c++
tags: [pattern, ranges]
title: Ranges & Views (C++20)
description: std::ranges algorithms, std::views::filter/transform/take/drop, pipe syntax (|), lazy evaluation, and range adaptors.
source: pattern
---

```c++
#include <iostream>
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
    std::cout << "\n";

    // --- take / drop ---
    auto first_three = numbers | std::views::take(3);
    std::cout << "First 3: ";
    for (int x : first_three) std::cout << x << " ";
    std::cout << "\n";

    auto after_five = numbers | std::views::drop(5);
    std::cout << "After 5: ";
    for (int x : after_five) std::cout << x << " ";
    std::cout << "\n";

    // --- Combining adaptors ---
    auto pipeline = numbers
        | std::views::filter([](int n) { return n > 3; })
        | std::views::transform([](int n) { return n * 10; })
        | std::views::take(4);

    std::cout << "Pipeline (>3 *10 take4): ";
    for (int x : pipeline) std::cout << x << " ";
    std::cout << "\n";

    // --- Lazy evaluation ---
    // Nothing is computed until we iterate
    auto lazy = numbers
        | std::views::transform([](int n) {
              std::cout << "  computing " << n << "\n";
              return n * 2;
          });
    std::cout << "Lazy -- not computed yet\n";
    for (int x : lazy | std::views::take(3))
        std::cout << "Got: " << x << "\n";

    // --- std::ranges algorithms ---
    std::vector<int> v = {5, 2, 8, 1, 9, 3, 7, 4, 6};
    std::ranges::sort(v);
    std::cout << "Sorted: ";
    for (int x : v) std::cout << x << " ";
    std::cout << "\n";

    auto it = std::ranges::find_if(v, [](int n) { return n > 5; });
    if (it != v.end())
        std::cout << "First >5: " << *it << "\n";

    // --- Views on a string ---
    std::string text = "Hello, World!";
    auto upper = text
        | std::views::transform([](char c) -> char {
              return static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
          });
    std::cout << "Uppercase: ";
    for (char c : upper) std::cout << c;
    std::cout << "\n";

    // --- Zip (C++23) ---
    // auto zipped = std::views::zip(v, numbers);
    // for (auto [a, b] : zipped)
    //     std::cout << a << " -> " << b << "\n";

    return 0;
}

```
