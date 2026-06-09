---
language: nix
tags: [pattern, nix]
title: Shell Environments
description: shell.nix / mkShell: buildInputs, nativeBuildInputs, shellHook, environment variables, and dev tooling.
source: pattern
---

```nix
# shell.nix — reproducible development environment
{ pkgs ? import <nixpkgs> { } }:

pkgs.mkShell {
  # --- Build dependencies ---
  buildInputs = with pkgs; [
    # Runtime libraries
    openssl
    zlib
    libffi
  ];

  # --- Build tools (propagated to build-time only) ---
  nativeBuildInputs = with pkgs; [
    # Core tools
    gcc
    cmake
    pkg-config
    makeWrapper

    # Language tooling
    python3
    nodejs_22
    cargo
    rustc
    rust-analyzer

    # Dev utilities
    git
    curl
    jq
    ripgrep
    fd
  ];

  # --- Shell startup hook ---
  shellHook = ''
    echo "Entering dev environment"
    echo "  Python: $(python3 --version)"
    echo "  Node:   $(node --version)"
    echo "  Rust:   $(rustc --version)"

    # Set project-specific environment
    export PROJECT_ROOT=$(pwd)
    export PATH=$PROJECT_ROOT/bin:$PATH
    export PS1="(dev) $PS1"

    # Source local env if available
    if [ -f .env ]; then
      set -a
      source .env
      set +a
    fi
  '';

  # --- Environment variables ---
  RUST_LOG = "info";
  EDITOR = "vim";
  NIX_ENFORCE_PURITY = "1";

  # --- Inputs from (optional) ---
  inputsFrom = [ ];
}

```
