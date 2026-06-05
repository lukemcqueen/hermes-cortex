---
language: c++
tags: [pattern, memory]
title: Smart Pointers & Memory
description: std::unique_ptr (exclusive ownership), std::shared_ptr (shared ownership), std::weak_ptr, std::make_unique, std::make_shared, aliasing, custom deleters.
source: pattern
---

```c++
#include <iostream>
#include <memory>
#include <string>
#include <vector>

struct Item {
    std::string name;
    explicit Item(std::string n) : name(std::move(n)) {
        std::cout << "Item created: " << name << "\n";
    }
    ~Item() { std::cout << "Item destroyed: " << name << "\n"; }
};

// Custom deleter
struct FileCloser {
    void operator()(FILE* f) const {
        if (f) {
            std::cout << "Closing file\n";
            fclose(f);
        }
    }
};

int main() {
    // --- unique_ptr (exclusive ownership) ---
    std::cout << "--- unique_ptr ---\n";
    {
        auto u1 = std::make_unique<Item>("unique1");
        // auto u2 = u1;            // error: no copy
        auto u2 = std::move(u1);    // ownership transfer
        if (!u1) std::cout << "u1 is now null\n";
        std::cout << "u2 owns: " << u2->name << "\n";
    }  // u2 destroyed

    // --- shared_ptr (shared ownership) ---
    std::cout << "\n--- shared_ptr ---\n";
    {
        auto s1 = std::make_shared<Item>("shared1");
        {
            auto s2 = s1;  // copy, refcount=2
            std::cout << "Use count: " << s1.use_count() << "\n";
        }  // refcount=1
        std::cout << "Use count: " << s1.use_count() << "\n";
    }  // refcount=0, destroyed

    // --- weak_ptr (non-owning observer) ---
    std::cout << "\n--- weak_ptr ---\n";
    std::weak_ptr<Item> wp;
    {
        auto sp = std::make_shared<Item>("temporary");
        wp = sp;
        if (auto locked = wp.lock())
            std::cout << "Locked: " << locked->name << "\n";
    }
    if (wp.expired())
        std::cout << "weak_ptr expired\n";

    // --- Custom deleter with unique_ptr ---
    std::cout << "\n--- Custom deleter ---\n";
    {
        std::unique_ptr<FILE, FileCloser> file(fopen("/dev/null", "w"));
        if (file) std::cout << "File opened\n";
    }  // FileCloser called

    // --- vector of unique_ptr ---
    std::cout << "\n--- vector<unique_ptr> ---\n";
    std::vector<std::unique_ptr<Item>> items;
    items.push_back(std::make_unique<Item>("vec_item"));

    return 0;
}

```
