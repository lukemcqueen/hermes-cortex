---
language: nix
tags: [pattern, nix]
title: Nix Packages & Search
description: nix search, nix edit, nix run, nix profile, nix why-depends, and nix store commands.
source: pattern
---

```nix
# Nix package management — essential commands

# --- Search packages ---
# nix search nixpkgs ripgrep
# nix search nixpkgs "python.*flask"

# --- View package source ---
# nix edit nixpkgs#hello        # open the Nix expression in $EDITOR
# nix edit nixpkgs#python3      # inspect Python derivation

# --- Run packages without installing ---
# nix run nixpkgs#hello         # run once (does not install to profile)
# nix run nixpkgs#cowsay -- "Hello, Nix!"

# --- Profile-based install ---
# nix profile install nixpkgs#ripgrep
# nix profile list
# nix profile upgrade '.*'
# nix profile remove ripgrep

# --- Dependency analysis ---
# nix why-depends nixpkgs#hello nixpkgs#glibc
# Shows why hello depends on glibc (the dependency chain)

# --- Store operations ---
# nix store --help
# nix store gc                    # garbage collect
# nix store optimise              # deduplicate store paths
# nix store diff-closures /proc/1/root ./result
# nix path-info --closure-size nixpkgs#hello

# --- Query derivations ---
# nix derivation show nixpkgs#hello
# nix derivation show nixpkgs#python3 --recursive | jq '.name'

```
