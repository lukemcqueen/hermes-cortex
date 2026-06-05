---
language: c++
tags: [pattern, containers]
title: STL Containers
description: vector, map, unordered_map, set, array, deque — construction, iteration, insertion, lookup, and when to use each.
source: pattern
---

```c++
#include <iostream>
#include <vector>
#include <map>
#include <unordered_map>
#include <set>
#include <array>
#include <deque>
#include <string>

int main() {
    // --- vector: dynamic contiguous array (use by default) ---
    std::vector<int> vec = {1, 2, 3, 4, 5};
    vec.push_back(6);
    std::cout << "vector back: " << vec.back() << ", size: " << vec.size() << "\n";

    // --- map: ordered key-value (red-black tree, O(log n)) ---
    std::map<std::string, int> ages;
    ages["Alice"] = 30;
    ages["Bob"] = 25;
    ages.insert({"Charlie", 35});
    for (const auto& [name, age] : ages)
        std::cout << name << ": " << age << "\n";

    // --- unordered_map: hash table (O(1) average) ---
    std::unordered_map<std::string, double> prices;
    prices["apple"] = 1.20;
    prices["banana"] = 0.80;

    // --- set: ordered unique elements ---
    std::set<int> unique = {3, 1, 4, 1, 5, 9, 2, 6, 5, 3};
    for (int x : unique) std::cout << x << " ";
    std::cout << "\n";

    // --- array: fixed-size stack array ---
    std::array<int, 4> fixed = {10, 20, 30, 40};
    std::cout << "array[2]: " << fixed[2] << "\n";

    // --- deque: double-ended queue ---
    std::deque<int> dq = {2, 3, 4};
    dq.push_front(1);
    dq.push_back(5);
    for (int x : dq) std::cout << x << " ";
    std::cout << "\n";

    // When to use each:
    // vector  – default; contiguous cache-friendly
    // deque   – push/pop both ends
    // map     – ordered lookups, range queries
    // unordered_map – fast hash lookups (no ordering)
    // set     – ordered unique collection
    // array   – compile-time fixed size on stack
    return 0;
}

```
