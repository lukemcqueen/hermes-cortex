---
language: nix
tags: [pattern, nix]
title: Derivations & Builds
description: Minimal stdenv.mkDerivation showing phases (unpack, configure, build, install), src, builder, and installPhase.
source: pattern
---

```nix
# A minimal Nix derivation using stdenv.mkDerivation
{ stdenv, fetchurl }:

stdenv.mkDerivation rec {
  pname = "hello";
  version = "2.12.1";

  src = fetchurl {
    url = "mirror://gnu/hello/${pname}-${version}.tar.gz";
    sha256 = "sha256-jZkUKv2VgYjB6G6VvD2hU1Ycq2Y0s2n0f0l0j0k0l0=";
  };

  # Phases: unpackPhase -> configurePhase -> buildPhase -> installPhase
  # Default phases work for autotools projects; override when needed.
  installPhase = ''
    mkdir -p $out/bin
    cp hello $out/bin/
  '';

  meta = with lib; {
    description = "A friendly program that prints a greeting";
    homepage = "https://www.gnu.org/software/hello/";
    license = licenses.gpl3Plus;
    maintainers = with maintainers; [ eelco ];
  };
}

```
