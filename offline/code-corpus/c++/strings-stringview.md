---
language: c++
tags: [pattern, strings]
title: Strings & String Views
description: std::string manipulation (find, replace, substr, append), std::string_view (C++17) for non-owning string references, to/from number conversions (std::to_string, stoi/stod).
source: pattern
---

```c++
#include <iostream>
#include <string>
#include <string_view>
#include <vector>
#include <charconv>  // std::from_chars (C++17)

int main() {
    // --- String construction & manipulation ---
    std::string s = "Hello, C++ World!";
    std::cout << "length: " << s.length() << "\n";

    // Find / replace / substr
    auto pos = s.find("C++");
    if (pos != std::string::npos)
        std::cout << "Found 'C++' at position " << pos << "\n";

    std::string sub = s.substr(7, 3);  // "C++"
    std::cout << "substr: '" << sub << "'\n";

    s.replace(pos, 3, "C++17");
    std::cout << "after replace: " << s << "\n";

    s.append(" is great!");
    std::cout << "after append: " << s << "\n";

    // --- String to/from number conversions ---
    // to_string
    std::string num_str = std::to_string(42);
    std::cout << "to_string(42): " << num_str << "\n";

    // stoi / stod / stoll
    std::string int_val = "1234";
    std::string dbl_val = "3.14159";
    int i = std::stoi(int_val);
    double d = std::stod(dbl_val);
    std::cout << "stoi: " << i << ", stod: " << d << "\n";

    // C++17 from_chars (no allocation, no exceptions)
    std::string number = "2024";
    int parsed = 0;
    auto [ptr, ec] = std::from_chars(number.data(),
                                     number.data() + number.size(), parsed);
    if (ec == std::errc{})
        std::cout << "from_chars: " << parsed << "\n";

    // --- string_view (C++17, non-owning) ---
    std::cout << "\n--- string_view ---\n";
    const char* raw = "This is a C-string";
    std::string_view sv(raw);  // no copy
    std::cout << "string_view: " << sv << "\n";
    std::cout << "first 4 chars: " << sv.substr(0, 4) << "\n";

    // Efficient splitting with string_view
    std::string_view csv = "apple,banana,cherry,date";
    std::vector<std::string_view> parts;
    size_t start = 0;
    while (start < csv.size()) {
        auto comma = csv.find(',', start);
        if (comma == std::string_view::npos) comma = csv.size();
        parts.push_back(csv.substr(start, comma - start));
        start = comma + 1;
    }
    for (auto part : parts)
        std::cout << "  part: '" << part << "'\n";

    return 0;
}

```
