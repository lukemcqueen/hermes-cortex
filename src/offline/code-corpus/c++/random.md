---
language: c++
tags: [pattern, random]
title: Random Number Generation
description: std::random_device (true randomness source), std::mt19937 (Mersenne Twister engine), uniform_int_distribution, normal_distribution, bernoulli_distribution.
source: pattern
---

```c++
#include <iostream>
#include <random>
#include <vector>
#include <algorithm>
#include <iomanip>

int main() {
    // --- Seed with true random (or fall back to deterministic) ---
    std::random_device rd;
    std::mt19937 gen(rd());  // Mersenne Twister

    // --- Uniform integer distribution ---
    std::uniform_int_distribution<int> die(1, 6);
    std::cout << "10 dice rolls: ";
    for (int i = 0; i < 10; ++i)
        std::cout << die(gen) << " ";
    std::cout << "\n";

    // --- Uniform real distribution ---
    std::uniform_real_distribution<double> uniform(0.0, 1.0);
    std::cout << "5 uniform reals: ";
    for (int i = 0; i < 5; ++i)
        std::cout << std::fixed << std::setprecision(4)
                  << uniform(gen) << " ";
    std::cout << "\n";

    // --- Normal (Gaussian) distribution ---
    std::normal_distribution<double> normal(50.0, 15.0);  // mean=50, stddev=15
    std::vector<int> histogram(100, 0);
    for (int i = 0; i < 10000; ++i) {
        double val = normal(gen);
        int bin = static_cast<int>(val);
        if (bin >= 0 && bin < 100) ++histogram[bin];
    }

    // Print a simple histogram
    std::cout << "\nNormal distribution histogram (mean=50, stddev=15):\n";
    for (int i = 15; i <= 85; ++i) {
        if (histogram[i] > 0) {
            std::cout << std::setw(3) << i << ": "
                      << std::string(histogram[i] / 100, '*') << "\n";
        }
    }

    // --- Bernoulli distribution (coin flip) ---
    std::bernoulli_distribution coin(0.7);  // 70% heads
    int heads = 0, tails = 0;
    for (int i = 0; i < 1000; ++i) {
        if (coin(gen)) ++heads;
        else ++tails;
    }
    std::cout << "\n1000 coin flips (p=0.7): heads=" << heads
              << " tails=" << tails << "\n";

    // --- Shuffle using random engine ---
    std::vector<int> cards(52);
    std::iota(cards.begin(), cards.end(), 1);
    std::shuffle(cards.begin(), cards.end(), gen);
    std::cout << "\nFirst 5 shuffled cards: ";
    for (int i = 0; i < 5; ++i)
        std::cout << cards[i] << " ";
    std::cout << "\n";

    return 0;
}

```
