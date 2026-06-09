---
language: c++
tags: [pattern, error-handling]
title: Exception Safety
description: try/catch, noexcept specifier, exception guarantees (basic/strong/nothrow), custom exception classes, and stack unwinding.
source: pattern
---

```c++
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

// ----- Custom exception -----
class CalculationError : public std::runtime_error {
public:
    explicit CalculationError(const std::string& msg, int code = -1)
        : std::runtime_error(msg), error_code_(code) {}

    int error_code() const noexcept { return error_code_; }

private:
    int error_code_;
};

// ----- noexcept guarantees -----
// Strong guarantee: either fully succeeds or leaves state unchanged
class Account {
    double balance_ = 0.0;
public:
    explicit Account(double initial) noexcept : balance_(initial) {}

    // Strong guarantee via copy-and-swap
    void deposit(double amount) {
        if (amount < 0)
            throw CalculationError("Negative deposit", 100);
        double new_balance = balance_ + amount;
        if (new_balance < balance_ && amount > 0)
            throw std::overflow_error("Overflow detected");
        balance_ = new_balance;  // commit — only one non-throwing assignment
    }

    double balance() const noexcept { return balance_; }
};

// noexcept move constructor
class Resource {
    int* data_ = nullptr;
public:
    Resource() : data_(new int[100]) {}
    ~Resource() { delete[] data_; }

    Resource(Resource&& other) noexcept : data_(std::exchange(other.data_, nullptr)) {}
    Resource& operator=(Resource&& other) noexcept {
        if (this != &other) {
            delete[] data_;
            data_ = std::exchange(other.data_, nullptr);
        }
        return *this;
    }

    Resource(const Resource&) = delete;
    Resource& operator=(const Resource&) = delete;
};

int main() {
    // Basic try/catch
    try {
        Account acct(100.0);
        acct.deposit(50.0);
        std::cout << "Balance: " << acct.balance() << "\n";
        acct.deposit(-10.0);  // throws
    } catch (const CalculationError& e) {
        std::cout << "Calculation error [" << e.error_code()
                  << "]: " << e.what() << "\n";
    } catch (const std::exception& e) {
        std::cout << "Standard error: " << e.what() << "\n";
    }

    // Stack unwinding example
    std::cout << "\n--- Stack unwinding ---\n";
    try {
        std::vector<int> vec(10, 42);
        std::cout << "vec[0] = " << vec[0] << "\n";
        // vec.at(100) throws std::out_of_range
        std::cout << "vec[100] = " << vec.at(100) << "\n";
        std::cout << "This line won't execute\n";
    } catch (const std::out_of_range& e) {
        std::cout << "Caught: " << e.what() << "\n";
    }
    std::cout << "Program continues after catch\n";

    return 0;
}

```
