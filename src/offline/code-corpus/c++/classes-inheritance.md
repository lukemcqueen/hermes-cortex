---
language: c++
tags: [pattern, oop]
title: Classes & Inheritance
description: Class definition, access control (public/protected/private), inheritance, virtual functions, override, and final specifiers.
source: pattern
---

```c++
#include <iostream>
#include <memory>
#include <vector>

class Animal {
public:
    virtual ~Animal() = default;
    virtual void speak() const = 0;
};

class Dog final : public Animal {
public:
    void speak() const override { std::cout << "Woof!\n"; }
};

class Cat final : public Animal {
public:
    void speak() const override { std::cout << "Meow!\n"; }
};

// Protected / private inheritance example
class Base {
protected:
    int protected_val_{42};
private:
    int private_val_{0};
};

class Derived : public Base {
public:
    int get_protected() const { return protected_val_; }
    // Cannot access private_val_
};

int main() {
    std::vector<std::unique_ptr<Animal>> animals;
    animals.push_back(std::make_unique<Dog>());
    animals.push_back(std::make_unique<Cat>());
    for (const auto& a : animals) a->speak();

    Derived d;
    std::cout << "Protected value: " << d.get_protected() << "\n";
    return 0;
}

```
