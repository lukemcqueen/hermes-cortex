---
language: c++
tags: [pattern, serialization]
title: Serialization
description: JSON serialization with nlohmann/json (single-header), binary serialization using stringstream, and protobuf notes.
source: pattern
---

```c++
#include <iostream>
#include <sstream>
#include <vector>
#include <string>
#include <cstdint>

// --- Binary serialization with stringstream ---
struct Player {
    std::string name;
    int level;
    double health;
    std::vector<int> inventory_ids;

    // Serialize to binary
    void serialize(std::ostream& os) const {
        size_t name_len = name.size();
        os.write(reinterpret_cast<const char*>(&name_len), sizeof(name_len));
        os.write(name.data(), name_len);
        os.write(reinterpret_cast<const char*>(&level), sizeof(level));
        os.write(reinterpret_cast<const char*>(&health), sizeof(health));
        size_t inv_size = inventory_ids.size();
        os.write(reinterpret_cast<const char*>(&inv_size), sizeof(inv_size));
        os.write(reinterpret_cast<const char*>(inventory_ids.data()),
                 inv_size * sizeof(int));
    }

    // Deserialize from binary
    void deserialize(std::istream& is) {
        size_t name_len;
        is.read(reinterpret_cast<char*>(&name_len), sizeof(name_len));
        name.resize(name_len);
        is.read(name.data(), name_len);
        is.read(reinterpret_cast<char*>(&level), sizeof(level));
        is.read(reinterpret_cast<char*>(&health), sizeof(health));
        size_t inv_size;
        is.read(reinterpret_cast<char*>(&inv_size), sizeof(inv_size));
        inventory_ids.resize(inv_size);
        is.read(reinterpret_cast<char*>(inventory_ids.data()),
                inv_size * sizeof(int));
    }
};

// --- Simple JSON-like builder (minimal, no external lib) ---
class SimpleJSON {
    std::ostringstream out_;
    bool first_ = true;
public:
    SimpleJSON& begin_object() {
        out_ << "{";
        first_ = true;
        return *this;
    }
    SimpleJSON& key(const std::string& k) {
        if (!first_) out_ << ",";
        out_ << "\"" << k << "\":";
        first_ = false;
        return *this;
    }
    SimpleJSON& value(const std::string& v) {
        out_ << "\"" << v << "\"";
        return *this;
    }
    SimpleJSON& value(int v) {
        out_ << v;
        return *this;
    }
    SimpleJSON& value(double v) {
        out_ << v;
        return *this;
    }
    SimpleJSON& end_object() {
        out_ << "}";
        return *this;
    }
    std::string str() const { return out_.str(); }
};

int main() {
    // --- Binary serialization ---
    Player p1{"Hero", 42, 95.5, {101, 202, 303}};
    std::stringstream buf;
    p1.serialize(buf);

    Player p2;
    p2.deserialize(buf);
    std::cout << "Deserialized: name=" << p2.name
              << " level=" << p2.level
              << " health=" << p2.health
              << " inventory=[";
    for (size_t i = 0; i < p2.inventory_ids.size(); ++i) {
        if (i) std::cout << ",";
        std::cout << p2.inventory_ids[i];
    }
    std::cout << "]\n";

    // --- Simple JSON ---
    SimpleJSON json;
    json.begin_object()
        .key("name").value("Hero")
        .key("level").value(42)
        .key("health").value(95.5)
        .key("alive").value("true")
        .end_object();
    std::cout << "JSON: " << json.str() << "\n";

    // --- Notes on nlohmann/json (single header) ---
    // #include <nlohmann/json.hpp>
    // using json = nlohmann::json;
    // json j = {{"name", "Hero"}, {"level", 42}};
    // auto name = j["name"].get<std::string>();
    //
    // --- Notes on protobuf ---
    // message Player {
    //   string name = 1;
    //   int32  level = 2;
    //   double health = 3;
    //   repeated int32 inventory_ids = 4;
    // }
    // Player p;
    // p.set_name("Hero");
    // p.SerializeToOstream(&output);
    // p.ParseFromIstream(&input);

    return 0;
}

```
