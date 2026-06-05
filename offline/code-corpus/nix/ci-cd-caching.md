---
language: nix
tags: [pattern, nix]
title: CI/CD & Caching
description: Nix build caching, Cachix, GitHub Actions Nix setup, Hydra basics, and Attic binary cache.
source: pattern
---

```nix
# Nix CI/CD and binary caching

# --- Cachix — hosted binary cache ---
# Install:
#   nix profile install nixpkgs#cachix
#   cachix use my-cache
#
# Push (from CI):
#   nix build .#packages.x86_64-linux.default
#   cachix push my-cache $(nix path-info .#packages.x86_64-linux.default)

# --- GitHub Actions — Nix setup ---
# .github/workflows/build.yml
# name: Build
# on: [push]
# jobs:
#   build:
#     runs-on: ubuntu-latest
#     steps:
#       - uses: actions/checkout@v4
#       - uses: cachix/install-nix-action@v27
#         with:
#           nix_path: nixpkgs=channel:nixos-unstable
#       - uses: cachix/cachix-action@v14
#         with:
#           name: my-cache
#           authToken: '${{ secrets.CACHIX_AUTH_TOKEN }}'
#       - run: nix build .#packages.x86_64-linux.default
#       - run: nix flake check

# --- Hydra (self-hosted CI) basics ---
# Hydra evaluates Nix expressions and builds derivations.
# Release.nix pattern:
# { nixpkgs ? import <nixpkgs> { } }:
# let
#   pkgs = nixpkgs;
# in
#   pkgs.releaseTools.aggregate {
#     name = "my-project";
#     constituents = [
#       pkgs.hello
#       pkgs.git
#     ];
#   }

# --- Attic (alternative binary cache) ---
#   attic login my-server https://attic.example.com
#   attic create my-cache
#   attic push my-cache ./result
#   attic configure my-cache my-server/my-cache

# --- Local binary cache ---
# Build and serve locally:
#   nix copy --to file:///tmp/nix-cache ./result
#   nix copy --from file:///tmp/nix-cache nixpkgs#hello

```
