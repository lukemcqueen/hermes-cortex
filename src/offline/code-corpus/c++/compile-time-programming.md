---
language: c++
tags: [pattern, metaprogramming]
title: Compile-Time Programming
description: constexpr functions, consteval (C++20), constinit (C++20), static_assert, template metaprogramming basics (compile-time factorial, prime check, type lists).
source: pattern
---

```c++
#include <iostream>
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
    std::cout << "factorial(10) = " << f10 << "\n";

    constexpr auto fib10 = fibonacci(10);
    std::cout << "fibonacci(10) = " << fib10 << "\n";

    constexpr bool p17 = is_prime(17);
    std::cout << "is_prime(17) = " << p17 << "\n";

    // consteval
    constexpr int s5 = square(5);
    std::cout << "square(5) = " << s5 << "\n";

    // constinit
    std::cout << "global_value = " << global_value << "\n";

    // Template metaprogramming results
    std::cout << "Factorial<6>::value = " << Factorial<6>::value << "\n";
    std::cout << "Sqrt<144>::value = " << Sqrt<144>::value << "\n";
    std::cout << "Sqrt<1000>::value = " << Sqrt<1000>::value << "\n";

    // Type list
    using Types = TypeList<int, double, char, float>;
    std::cout << "TypeList size = " << Length<Types>::value << "\n";

    // Run-time check of compile-time constants
    constexpr int computed = [] {
        int sum = 0;
        for (int i = 1; i <= 10; ++i)
            if (is_prime(i)) sum += i;
        return sum;
    }();  // IIFE lambda, evaluated at compile time
    std::cout << "Sum of primes <= 10: " << computed << "\n";

    return 0;
}

```
