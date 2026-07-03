---
language: python
tags: [cli, sys]
title: Argparse CLI
description: Build a command-line interface with argparse: flags, positional args, subcommands.
source: pattern
---

```python
import argparse

def main():
    parser = argparse.ArgumentParser(description='Tool description')
    parser.add_argument('input', help='Input file path')
    parser.add_argument('-o', '--output', default='out.txt', help='Output file')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--limit', type=int, default=10, help='Max results')

    args = parser.parse_args()

    if args.verbose:
        print(f'Processing {args.input} -> {args.output}')

    # Your logic here
    with open(args.input) as f:
        data = f.read()

    print(f'Done. Read {len(data)} bytes.')

if __name__ == '__main__':
    main()

```
