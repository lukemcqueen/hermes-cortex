---
language: c++
tags: [pattern, io]
title: File I/O & Streams
description: fstream/ifstream/ofstream for file I/O, stringstream for in-memory formatting, getline for line-based input, binary I/O, and stream states.
source: pattern
---

```c++
#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

int main() {
    // --- Writing to a file ---
    {
        std::ofstream out("example.txt");
        if (!out) {
            std::cerr << "Failed to write\n";
            return 1;
        }
        out << "Hello, file!\n";
        out << "Line 2: " << 42 << "\n";
    }  // out closes automatically (RAII)

    // --- Reading line by line ---
    {
        std::ifstream in("example.txt");
        if (!in) {
            std::cerr << "Failed to read\n";
            return 1;
        }
        std::string line;
        while (std::getline(in, line)) {
            std::cout << "Read: " << line << "\n";
        }
    }

    // --- StringStream (in-memory parsing) ---
    {
        std::string data = "Alice 30 85.5\nBob 25 92.3\n";
        std::istringstream iss(data);
        std::string name;
        int age;
        double score;
        while (iss >> name >> age >> score) {
            std::cout << name << " is " << age
                      << " years old, score: " << score << "\n";
        }
    }

    // --- Binary I/O ---
    {
        struct Record { int id; double value; };
        Record wr{1, 3.14159};

        // Write binary
        std::ofstream bout("data.bin", std::ios::binary);
        bout.write(reinterpret_cast<const char*>(&wr), sizeof(wr));
        bout.close();

        // Read binary
        Record rd;
        std::ifstream bin("data.bin", std::ios::binary);
        bin.read(reinterpret_cast<char*>(&rd), sizeof(rd));
        std::cout << "Binary read: id=" << rd.id << ", value=" << rd.value << "\n";
    }

    // --- Stream states ---
    {
        std::ifstream f("nonexistent.txt");
        if (!f.good()) {
            std::cout << "Stream state: fail=" << f.fail()
                      << " eof=" << f.eof() << " bad=" << f.bad() << "\n";
        }
    }

    return 0;
}

```
