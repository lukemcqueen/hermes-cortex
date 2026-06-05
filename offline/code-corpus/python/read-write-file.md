---
language: python
tags: [io, file]
title: Read/Write File
description: Read and write text files safely with context managers.
source: pattern
---

```python
# Read entire file
with open('file.txt', 'r') as f:
    content = f.read()

# Read line by line
with open('file.txt', 'r') as f:
    for line in f:
        print(line.strip())

# Write file
with open('file.txt', 'w') as f:
    f.write('hello\n')

# Append
with open('file.txt', 'a') as f:
    f.write('more data\n')

# Read JSON
import json
with open('data.json') as f:
    data = json.load(f)

# Write JSON
with open('data.json', 'w') as f:
    json.dump(data, f, indent=2)
```
