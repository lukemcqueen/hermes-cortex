---
language: nix
tags: [pattern, nix]
title: Overlays & Overrides
description: final:prev pattern, overlay composition, override, overrideAttrs, and packageOverride.
source: pattern
---

```nix
# Overlays and overrides in Nix

# --- Overlay pattern (final: prev: ...) ---
# Place in ~/.config/nixpkgs/overlays/ or nixpkgs.overlays
self: super:

{
  # Replace hello with a custom version
  hello = super.hello.overrideAttrs (old: {
    patches = [ ./custom-hello.patch ];
    postInstall = old.postInstall or "" + ''
      echo "Custom build complete!"
    '';
  });

  # Add a new package
  my-tool = super.callPackage ./pkgs/my-tool { };
}

# --- Combining overlays ---
# nixpkgs.overlays = [
#   (import ./overlays/rust-overlay)
#   (import ./overlays/emacs-overlay)
# ];

# --- override (function arguments) ---
# original package: { enableFoo ? false, ... }: ...
# my-pkg = pkgs.somePkg.override { enableFoo = true; };

# --- overrideAttrs (derivation attributes) ---
# pkgs.hello.overrideAttrs (old: {
#   buildInputs = old.buildInputs ++ [ pkgs.libfoo ];
#   cmakeFlags = old.cmakeFlags or [] ++ [ "-DWITH_FOO=ON" ];
# });

# --- Practical overlay example ---
final: prev: {
  # Pin a specific version
  python3 = prev.python312;

  # Apply patches
  curl = prev.curl.overrideAttrs (_: {
    patches = [ ./curl-patch.patch ];
  });

  # Add packages from nixpkgs unstable
  unstable = import <nixpkgs-unstable> {
    system = final.system;
    config.allowUnfree = true;
  };
}

```
