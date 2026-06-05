---
language: c++
tags: [pattern, algorithms]
title: STL Algorithms
description: sort, find_if, accumulate, transform, copy_if, and the erase-remove idiom.
source: pattern
---

```c++
#include <iostream>
#include <vector>
#include <algorithm>
#include <numeric>
#include <string>

int main() {
    std::vector<int> v = {3, 1, 4, 1, 5, 9, 2, 6, 5, 3};

    // --- sort ---
    std::sort(v.begin(), v.end());
    for (int x : v) std::cout << x << " ";
    std::cout << "\n";

    // --- find_if ---
    auto it = std::find_if(v.begin(), v.end(), [](int n) { return n > 5; });
    if (it != v.end())
        std::cout << "First >5: " << *it << "\n";

    // --- accumulate ---
    int sum = std::accumulate(v.begin(), v.end(), 0);
    std::cout << "Sum: " << sum << "\n";

    // --- transform ---
    std::vector<int> squares(v.size());
    std::transform(v.begin(), v.end(), squares.begin(),
                   [](int n) { return n * n; });
    for (int x : squares) std::cout << x << " ";
    std::cout << "\n";

    // --- copy_if ---
    std::vector<int> evens;
    std::copy_if(v.begin(), v.end(), std::back_inserter(evens),
                 [](int n) { return n % 2 == 0; });
    for (int x : evens) std::cout << x << " ";
    std::cout << "\n";

    // --- erase-remove idiom ---
    std::vector<int> w = {1, 2, 3, 2, 4, 2, 5};
    w.erase(std::remove(w.begin(), w.end(), 2), w.end());
    for (int x : w) std::cout << x << " ";
    std::cout << "\n";

    return 0;
}

```
