---
language: nix
tags: [pattern, nix]
title: Flakes
description: Modern flake.nix with inputs/outputs, nixpkgs, flake-utils, nix flake commands, and lock file basics.
source: pattern
---

```nix
# flake.nix — modern Nix project structure
{
  description = "A flake-powered Nix project";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
      in
      {
        packages.default = pkgs.hello;

        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [ git curl ];
          shellHook = ''
            echo "Welcome to the dev shell!"
          '';
        };
      }
    );
}

# --- Common nix flake commands ---
# nix flake init       # create a flake.nix in current dir
# nix flake check      # evaluate & check the flake
# nix flake show       # show all outputs
# nix flake update     # update lock file entries
# nix flake lock       # create/update flake.lock
# nix develop          # enter dev shell
# nix build .#default  # build the default package

```
