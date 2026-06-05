---
language: nix
tags: [pattern, nix]
title: Nix Expressions & Language
description: Core language features: let/in, with, inherit, rec, attrset/list, function, import, callPackage.
source: pattern
---

```nix
# Nix expression language — core constructs

# --- let/in: local bindings ---
let
  x = 42;
  y = x * 2;
in
  x + y  # -> 126

# --- rec: recursive attribute set (self-referencing) ---
rec {
  a = 1;
  b = a + 1;  # refers to a in the same set
  c = b + 1;
}

# --- inherit: pull names from scope ---
let
  pkgs = import <nixpkgs> {};
in
  pkgs.stdenv.mkDerivation {
    name = "example";
    inherit (pkgs) fetchurl;  # equivalent to fetchurl = pkgs.fetchurl
    inherit (pkgs) stdenv;    # same pattern for multiple attrs
  }

# --- with: bring attrs into scope ---
let
  pkgs = import <nixpkgs> {};
in
  with pkgs; [ hello git curl ]
  # -> [ <derivation hello> <derivation git> <derivation curl> ]

# --- attrset & list literal ---
{
  list_example = [ 1 2 3 ];
  attrset_example = { a = 1; b = 2; };
  nested = {
    deep = "value";
  };
}

# --- function & callPackage pattern ---
{ stdenv, lib, fetchurl, ... }:   # function pattern (destructured attrs)
stdenv.mkDerivation {
  name = "example";
  src = fetchurl { url = "..."; sha256 = "..."; };
}

# --- import ---
# myfile.nix content:
# { greeting }: "Hello, ${greeting}!"
#
# Usage:
# let
#   f = import ./myfile.nix;
# in
#   f { greeting = "world"; }

```
