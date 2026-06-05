---
language: c++
tags: [pattern, memory]
title: RAII & Destructors
description: Constructor/destructor, Rule of Five, move semantics, and smart pointer RAII wrappers (unique_ptr, shared_ptr, weak_ptr).
source: pattern
---

```c++
#include <iostream>
#include <cstring>
#include <utility>

// Rule-of-Five class: manages a dynamically allocated C-string
class StringBuffer {
    char* data_;
    std::size_t size_;

public:
    // Constructor
    explicit StringBuffer(const char* str)
        : size_(std::strlen(str))
        , data_(new char[size_ + 1])
    {
        std::strcpy(data_, str);
        std::cout << "Constructed: " << data_ << "\n";
    }

    // Destructor
    ~StringBuffer() {
        std::cout << "Destructed: " << (data_ ? data_ : "nullptr") << "\n";
        delete[] data_;
    }

    // Copy constructor
    StringBuffer(const StringBuffer& other)
        : size_(other.size_)
        , data_(new char[size_ + 1])
    {
        std::strcpy(data_, other.data_);
        std::cout << "Copy constructed\n";
    }

    // Copy assignment
    StringBuffer& operator=(const StringBuffer& other) {
        if (this != &other) {
            delete[] data_;
            size_ = other.size_;
            data_ = new char[size_ + 1];
            std::strcpy(data_, other.data_);
            std::cout << "Copy assigned\n";
        }
        return *this;
    }

    // Move constructor
    StringBuffer(StringBuffer&& other) noexcept
        : data_(other.data_)
        , size_(other.size_)
    {
        other.data_ = nullptr;
        other.size_ = 0;
        std::cout << "Move constructed\n";
    }

    // Move assignment
    StringBuffer& operator=(StringBuffer&& other) noexcept {
        if (this != &other) {
            delete[] data_;
            data_ = other.data_;
            size_ = other.size_;
            other.data_ = nullptr;
            other.size_ = 0;
            std::cout << "Move assigned\n";
        }
        return *this;
    }

    const char* c_str() const { return data_; }
};

int main() {
    StringBuffer a("Hello, RAII!");
    StringBuffer b = a;            // copy
    StringBuffer c = std::move(a); // move
    b = c;                         // copy assign
    b = std::move(c);              // move assign
    return 0;
}

```
