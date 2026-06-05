---
language: c++
tags: [pattern, metaprogramming]
title: Type Traits & SFINAE
description: std::is_integral, std::is_floating_point, std::enable_if, std::conditional, std::void_t, and C++20 concepts requires clause.
source: pattern
---

```c++
#include <iostream>
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
    std::cout << "twice(21): " << twice(21) << "\n";
    std::cout << "twice(3.14): " << twice(3.14) << "\n";
    std::cout << "add_ten(100): " << add_ten(100) << "\n";

    // --- void_t detection ---
    std::cout << "std::vector has value_type? "
              << has_value_type<std::vector<int>>::value << "\n";
    std::cout << "int has value_type? "
              << has_value_type<int>::value << "\n";

    // --- std::conditional ---
    PrecisionType<true> float_val = 3.14f;  // float
    PrecisionType<false> double_val = 3.1415926535;  // double
    std::cout << "float precision: " << float_val << "\n";
    std::cout << "double precision: " << double_val << "\n";

    // --- C++20 concepts ---
    static_assert(Integer<int>);
    static_assert(!Integer<std::string>);
    static_assert(SignedInteger<int>);
    static_assert(!SignedInteger<unsigned int>);
    static_assert(Incrementable<int>);

    auto constrained_fn = []<Integer T>(T a, T b) {
        return a + b;
    };
    std::cout << "constrained_fn(3, 4): " << constrained_fn(3, 4) << "\n";

    return 0;
}

```
