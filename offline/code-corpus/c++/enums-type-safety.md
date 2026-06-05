---
language: c++
tags: [pattern, types]
title: Enums & Type Safety
description: enum class (scoped enums), underlying type specification, switch exhaustiveness, and conversion to/from integral types.
source: pattern
---

```c++
#include <iostream>
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
    std::cout << "Color: " << to_string(c) << "\n";
    std::cout << "As int: " << to_integral(c) << "\n";

    // Switch exhaustiveness
    switch (c) {
        case Color::Red:    std::cout << "Red\n"; break;
        case Color::Green:  std::cout << "Green\n"; break;
        case Color::Blue:   std::cout << "Blue\n"; break;
        case Color::Yellow: std::cout << "Yellow\n"; break;
    }

    // Flags
    Permission perms = Permission::Read | Permission::Write;
    std::cout << "Can read?  " << has_flag(perms, Permission::Read) << "\n";
    std::cout << "Can exec?  " << has_flag(perms, Permission::Execute) << "\n";

    // Iteration workaround
    std::cout << "\nAll colors:\n";
    for (int i = 0; i <= 3; ++i) {
        Color col = static_cast<Color>(i);
        std::cout << "  " << to_string(col) << " (" << to_integral(col) << ")\n";
    }

    return 0;
}

```
