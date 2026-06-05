---
language: nix
tags: [pattern, nix]
title: Development with nix develop
description: devShell, nix develop vs nix-shell, build inputs, run inputs, and using flakes for development.
source: pattern
---

```nix
# nix develop — flake-based dev shells

# --- devShell in flake.nix ---
# outputs = { self, nixpkgs, ... }: let
#   pkgs = import nixpkgs { system = "x86_64-linux"; };
# in {
#   devShells.x86_64-linux = {
#     default = pkgs.mkShell {
#       packages = with pkgs; [ go gopls delve ];
#       shellHook = ''echo "Go dev environment ready"'';
#     };
#
#     ci = pkgs.mkShell {
#       packages = with pkgs; [ go gopkgs ];
#     };
#   };
# };

# --- Usage ---
# nix develop                # enter default devShell
# nix develop .#ci           # enter 'ci' devShell
# nix develop --command go test   # run command inside shell

# --- nix-shell compatibility ---
# nix develop on a directory with shell.nix (flakes disabled):
# nix develop --impure .#default

# --- Pinned inputs for reproducibility ---
# inputs = {
#   nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
#   nixpkgs-unstable.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
#   flake-utils.url = "github:numtide/flake-utils";
# };

# --- Multi-shell project example ---
# outputs = { self, nixpkgs, flake-utils, ... }:
#   flake-utils.lib.eachDefaultSystem (system: {
#     devShells = {
#       frontend = pkgs.mkShell { packages = with pkgs; [ nodejs yarn ]; };
#       backend  = pkgs.mkShell { packages = with pkgs; [ python3 poetry ]; };
#       default  = pkgs.mkShell { packages = with pkgs; [ nodejs python3 ]; };
#     };
#   });
#
# cd project && nix develop .#backend

```
