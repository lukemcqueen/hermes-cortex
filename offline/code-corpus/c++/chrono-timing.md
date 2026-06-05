---
language: c++
tags: [pattern, time]
title: Chrono & Timing
description: std::chrono::duration, time_point, high_resolution_clock, system_clock::now, sleep_for, and measuring elapsed time.
source: pattern
---

```c++
#include <iostream>
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
    std::cout << "500ms = " << ms.count() << " ms\n";
    std::cout << "2s = " << sec.count() << " s\n";

    // --- Timing a function with high_resolution_clock ---
    auto start = std::chrono::high_resolution_clock::now();

    std::this_thread::sleep_for(250ms);  // simulate work

    auto end = std::chrono::high_resolution_clock::now();
    auto elapsed = std::chrono::duration_cast<std::chrono::microseconds>(end - start);

    std::cout << "Elapsed: " << elapsed.count() << " us"
              << " (" << elapsed.count() / 1000.0 << " ms)\n";

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
    std::cout << "diff in ns:  " << diff.count() << "\n";
    std::cout << "diff in ms:  "
              << std::chrono::duration_cast<std::chrono::milliseconds>(diff).count()
              << "\n";
    std::cout << "diff in s:   "
              << std::chrono::duration_cast<std::chrono::seconds>(diff).count()
              << "\n";

    // --- Timepoints and duration math ---
    auto later = now + 1h + 30min;  // 1.5 hours from now
    std::time_t later_tt = std::chrono::system_clock::to_time_t(later);
    std::cout << "1.5h from now: " << std::ctime(&later_tt);

    // --- C++20 chrono::parse / formatting ---
    // Uncomment if using C++20:
    // auto tp = std::chrono::system_clock::now();
    // std::cout << std::format("{:%Y-%m-%d %H:%M:%S}", tp) << "\n";

    return 0;
}

```
