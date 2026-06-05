"""Infra² snippets — 20 entries combining Nix (10) and PowerShell (10).

Nix patterns: derivations, expressions, flakes, home-manager, NixOS modules,
overlays, mkShell, nix develop, nix search/profile, CI/caching.

PowerShell patterns: cmdlets, filesystem/registry, modules, error handling,
advanced functions, remoting/CIM, Active Directory, logging/transcripts,
WMI/system, REST/JSON.
"""

SNIPPETS = [
    # ═══════════════════════════════════════════════════════════
    # NIX 1 — Derivations & Builds
    # ═══════════════════════════════════════════════════════════
    ("nix/derivations.md", "nix", ["pattern", "nix"],
     "Derivations & Builds",
     "Minimal stdenv.mkDerivation showing phases (unpack, configure, build, install), src, builder, and installPhase.",
     "pattern",
     r"""# A minimal Nix derivation using stdenv.mkDerivation
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
"""),

    # ═══════════════════════════════════════════════════════════
    # NIX 2 — Nix Expressions & Language
    # ═══════════════════════════════════════════════════════════
    ("nix/expressions.md", "nix", ["pattern", "nix"],
     "Nix Expressions & Language",
     "Core language features: let/in, with, inherit, rec, attrset/list, function, import, callPackage.",
     "pattern",
     r"""# Nix expression language — core constructs

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
"""),

    # ═══════════════════════════════════════════════════════════
    # NIX 3 — Flakes
    # ═══════════════════════════════════════════════════════════
    ("nix/flakes.md", "nix", ["pattern", "nix"],
     "Flakes",
     "Modern flake.nix with inputs/outputs, nixpkgs, flake-utils, nix flake commands, and lock file basics.",
     "pattern",
     r"""# flake.nix — modern Nix project structure
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
"""),

    # ═══════════════════════════════════════════════════════════
    # NIX 4 — Home Manager
    # ═══════════════════════════════════════════════════════════
    ("nix/home-manager.md", "nix", ["pattern", "nix"],
     "Home Manager",
     "home.nix configuration: programs, services, home.packages, home.file, and nixpkgs.config.",
     "pattern",
     r"""# home.nix — Home Manager configuration
{ config, pkgs, ... }:

{
  # --- Packages to install ---
  home.packages = with pkgs; [
    htop
    git
    ripgrep
    fd
    neovim
    tmux
  ];

  # --- Program configuration ---
  programs = {
    git = {
      enable = true;
      userName = "Your Name";
      userEmail = "you@example.com";
      extraConfig = {
        init.defaultBranch = "main";
        pull.rebase = true;
      };
    };

    bash = {
      enable = true;
      initExtra = ''
        export EDITOR=nvim
        alias ll='ls -la'
      '';
    };

    starship = {
      enable = true;
      settings = {
        add_newline = true;
        character = {
          success_symbol = "[->](green)";
          error_symbol = "[->](red)";
        };
      };
    };
  };

  # --- Services (user-level systemd units) ---
  services = {
    syncthing = {
      enable = true;
    };
  };

  # --- Manage dotfiles ---
  home.file = {
    ".config/nvim/init.lua".source = ./dotfiles/init.lua;
    ".tmux.conf".text = ''
      set -g mouse on
      set -g default-terminal "tmux-256color"
    '';
  };

  # --- Nixpkgs config (allow unfree etc.) ---
  nixpkgs.config = {
    allowUnfree = true;
  };

  # --- State version (required) ---
  home.stateVersion = "24.11";
}
"""),

    # ═══════════════════════════════════════════════════════════
    # NIX 5 — NixOS Modules
    # ═══════════════════════════════════════════════════════════
    ("nix/nixos-modules.md", "nix", ["pattern", "nix"],
     "NixOS Modules",
     "Module system: imports, options, config, mkIf, mkMerge, types, and conditional configuration.",
     "pattern",
     r"""# NixOS module — declarative system configuration
{ config, lib, pkgs, ... }:

with lib;

let
  cfg = config.services.my-service;
in
{
  # --- Options declaration (the interface) ---
  options.services.my-service = {
    enable = mkEnableOption "my custom service";

    port = mkOption {
      type = types.port;
      default = 8080;
      description = "TCP port to listen on";
    };

    package = mkPackageOption pkgs "hello" { };

    extraConfig = mkOption {
      type = types.lines;
      default = "";
      description = "Extra config appended to the config file";
    };
  };

  # --- Config (the implementation) ---
  config = mkIf cfg.enable {
    # Import other modules conditionally
    imports = [
      ./hardware-configuration.nix
    ];

    # System packages
    environment.systemPackages = with pkgs; [
      cfg.package
      curl
    ];

    # Systemd service
    systemd.services.my-service = {
      description = "My Custom Service";
      wantedBy = [ "multi-user.target" ];
      after = [ "network.target" ];
      serviceConfig = {
        ExecStart = "${cfg.package}/bin/hello --port ${toString cfg.port}";
        Restart = "on-failure";
        DynamicUser = true;
      };
    };

    # Firewall
    networking.firewall.allowedTCPPorts = [ cfg.port ];
  };
}

# --- Common merge patterns ---
# mkMerge: combine configs from different conditions
# config = mkMerge [
#   (mkIf (cfg.enable) { ... })
#   (mkIf (cfg.useTLS) { ... })
# ];
#
# mkIf: conditional config (produces an empty set when false)
"""),

    # ═══════════════════════════════════════════════════════════
    # NIX 6 — Overlays & Overrides
    # ═══════════════════════════════════════════════════════════
    ("nix/overlays.md", "nix", ["pattern", "nix"],
     "Overlays & Overrides",
     "final:prev pattern, overlay composition, override, overrideAttrs, and packageOverride.",
     "pattern",
     r"""# Overlays and overrides in Nix

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
"""),

    # ═══════════════════════════════════════════════════════════
    # NIX 7 — Shell Environments (mkShell)
    # ═══════════════════════════════════════════════════════════
    ("nix/shell-environments.md", "nix", ["pattern", "nix"],
     "Shell Environments",
     "shell.nix / mkShell: buildInputs, nativeBuildInputs, shellHook, environment variables, and dev tooling.",
     "pattern",
     r"""# shell.nix — reproducible development environment
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
"""),

    # ═══════════════════════════════════════════════════════════
    # NIX 8 — Development with `nix develop`
    # ═══════════════════════════════════════════════════════════
    ("nix/nix-develop.md", "nix", ["pattern", "nix"],
     "Development with nix develop",
     "devShell, nix develop vs nix-shell, build inputs, run inputs, and using flakes for development.",
     "pattern",
     r"""# nix develop — flake-based dev shells

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
"""),

    # ═══════════════════════════════════════════════════════════
    # NIX 9 — Nix Packages & Search
    # ═══════════════════════════════════════════════════════════
    ("nix/nix-packages-search.md", "nix", ["pattern", "nix"],
     "Nix Packages & Search",
     "nix search, nix edit, nix run, nix profile, nix why-depends, and nix store commands.",
     "pattern",
     r"""# Nix package management — essential commands

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
"""),

    # ═══════════════════════════════════════════════════════════
    # NIX 10 — CI/CD & Caching
    # ═══════════════════════════════════════════════════════════
    ("nix/ci-cd-caching.md", "nix", ["pattern", "nix"],
     "CI/CD & Caching",
     "Nix build caching, Cachix, GitHub Actions Nix setup, Hydra basics, and Attic binary cache.",
     "pattern",
     r"""# Nix CI/CD and binary caching

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
"""),

    # ═══════════════════════════════════════════════════════════
    # POWERSHELL 1 — Cmdlets & Pipeline
    # ═══════════════════════════════════════════════════════════
    ("powershell/cmdlets-pipeline.md", "powershell", ["pattern", "powershell"],
     "Cmdlets & Pipeline",
     "Get-Command, Get-Help, Where-Object, Select-Object, ForEach-Object, and pipeline object binding.",
     "pattern",
     r"""# Cmdlets and the PowerShell pipeline

# --- Discover cmdlets ---
Get-Command -Verb Get          # all cmdlets that 'Get' something
Get-Command -Noun Process      # all *-Process cmdlets
Get-Command -Module ActiveDirectory

# --- Get help ---
Get-Help Get-Process
Get-Help Get-Process -Examples
Get-Help about_Pipelines       # conceptual help

# --- Pipeline basics ---
# Objects flow through the pipeline, not text
Get-Process |
    Where-Object { $_.WorkingSet64 -gt 100MB } |
    Select-Object Name, Id, @{Name='MemMB';Expression={[math]::Round($_.WorkingSet64/1MB,2)}} |
    Sort-Object MemMB -Descending |
    Format-Table -AutoSize

# --- ForEach-Object ---
Get-Service |
    ForEach-Object {
        [PSCustomObject]@{
            ServiceName = $_.Name
            Status      = $_.Status
            StartType   = $_.StartType
        }
    }

# --- Pipeline bound parameters ---
# Cmdlets that accept pipeline input by value or by property name
Get-Process | Stop-Process -WhatIf   # pipe process objects directly
Get-Content servers.txt | Test-Connection -Count 1

# --- Custom pipeline function ---
function Add-Numbers {
    [CmdletBinding()]
    param(
        [Parameter(ValueFromPipeline)]
        [int[]]$Number
    )
    begin { $sum = 0 }
    process { $sum += $_ }
    end { $sum }
}
1..10 | Add-Numbers  # returns 55
"""),

    # ═══════════════════════════════════════════════════════════
    # POWERSHELL 2 — Filesystem & Registry
    # ═══════════════════════════════════════════════════════════
    ("powershell/filesystem-registry.md", "powershell", ["pattern", "powershell"],
     "Filesystem & Registry",
     "Get-ChildItem, Set-Location, Get-Content, Set-Content, Copy/Move/Remove-Item, and registry as a PSDrive.",
     "pattern",
     r"""# Filesystem and Registry operations

# --- Navigation ---
Set-Location C:\Projects
Get-Location
Push-Location C:\Windows\System32
Pop-Location

# --- List contents ---
Get-ChildItem                     # ls equivalent
Get-ChildItem -Recurse -Filter *.ps1
Get-ChildItem -Directory          # directories only
Get-ChildItem -File               # files only
Get-ChildItem -Hidden             # hidden items

# --- File content ---
Get-Content .\log.txt             # read file
Get-Content .\log.txt -Tail 50    # last 50 lines (tail -f with -Wait)
Set-Content .\output.txt -Value "Hello, World!"
Add-Content .\log.txt -Value "New log entry"

# --- Copy / Move / Remove ---
Copy-Item .\source.txt .\dest.txt -Force
Move-Item .\old.txt .\new.txt
Remove-Item .\temp.txt -Confirm

# New-Item (creates files and directories)
New-Item -ItemType Directory -Path .\scripts -Force
New-Item -ItemType File -Path .\scripts\deploy.ps1 -Force

# --- Registry as a PSDrive ---
# Registry drives: HKLM:, HKCU:
Set-Location HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion

Get-ChildItem                        # list registry keys
Get-ItemProperty .                    # get values of current key
Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion" -Name ProductName

# Create/modify registry key
New-Item -Path HKCU:\Software\MyApp
Set-ItemProperty -Path HKCU:\Software\MyApp -Name Setting -Value "enabled"

# Remove registry key
Remove-Item -Path HKCU:\Software\MyApp -Recurse
"""),

    # ═══════════════════════════════════════════════════════════
    # POWERSHELL 3 — Modules & Scripts
    # ═══════════════════════════════════════════════════════════
    ("powershell/modules-scripts.md", "powershell", ["pattern", "powershell"],
     "Modules & Scripts",
     ".psm1, .psd1, Import-Module, script scope, dot sourcing, and module manifests.",
     "pattern",
     r"""# PowerShell modules and scripts

# --- Script file (.ps1) ---
# myscript.ps1
Write-Host "Running script"
$privateVar = "script-scoped"

function Get-Secret {
    param([string]$Name)
    return "secret-$Name"
}

# --- Module (.psm1) ---
# MyModule/MyModule.psm1
$script:ModuleVersion = "1.0.0"

function Get-MyModuleInfo {
    return "MyModule v$script:ModuleVersion"
}

function Set-MyConfiguration {
    param([string]$ConfigPath)
    $script:ConfigPath = $ConfigPath
}

# Export only specific functions
Export-ModuleMember -Function Get-MyModuleInfo, Set-MyConfiguration

# --- Module manifest (.psd1) ---
# MyModule/MyModule.psd1
@{
    RootModule           = 'MyModule.psm1'
    ModuleVersion        = '1.0.0'
    GUID                 = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
    Author               = 'Your Name'
    CompanyName          = 'Your Company'
    Copyright            = '(c) 2024 Your Name'
    Description          = 'Sample PowerShell module'
    PowerShellVersion    = '7.0'
    FunctionsToExport    = @('Get-MyModuleInfo', 'Set-MyConfiguration')
    CmdletsToExport      = @()
    VariablesToExport    = @()
    AliasesToExport      = @()
}

# --- Import module ---
Import-Module .\MyModule
Import-Module .\MyModule -Force        # re-import after changes
Import-Module ActiveDirectory          # from module path
Get-Module -ListAvailable               # see installed modules

# --- Dot sourcing (runs in current scope) ---
. .\utils.ps1                           # brings functions into global scope
# vs
.\utils.ps1                             # runs in child scope -- vars not persisted

# --- Module scope ---
# $script:     -- script/module scope
# $private:    -- private (not exported)
# $global:     -- visible everywhere
# $local:      -- current scope (default)
"""),

    # ═══════════════════════════════════════════════════════════
    # POWERSHELL 4 — Error Handling
    # ═══════════════════════════════════════════════════════════
    ("powershell/error-handling.md", "powershell", ["pattern", "powershell"],
     "Error Handling",
     "try/catch/finally, $Error, $?, -ErrorAction, trap, and $LASTEXITCODE for native commands.",
     "pattern",
     r"""# Error handling in PowerShell

# --- try / catch / finally ---
try {
    Get-Item "C:\nonexistent\file.txt" -ErrorAction Stop
    Write-Host "File found"
}
catch [System.Management.Automation.ItemNotFoundException] {
    Write-Warning "File not found: $_"
}
catch {
    Write-Error "Unexpected error: $_"
}
finally {
    Write-Debug "Cleanup runs regardless of success or failure"
}

# --- ErrorAction parameters ---
Get-Item "bad.txt" -ErrorAction SilentlyContinue   # suppress, no $?
Get-Item "bad.txt" -ErrorAction Stop                # make terminating
Get-Item "bad.txt" -ErrorAction Continue             # default -- print & continue
Get-Item "bad.txt" -ErrorAction Inquire              # prompt on error

# --- $Error automatic variable ---
# $Error is a stack -- most recent first
$Error[0]                    # most recent error
$Error.Count                 # number of errors in session
$Error.Clear()               # clear error list
$ErrorView = "CategoryView"  # compact error display

# --- $? (previous command success) ---
# Boolean: $true if last command succeeded, $false otherwise
if (-not $?) {
    Write-Warning "Last command failed"
}

# --- trap (legacy, scoped) ---
trap {
    Write-Warning "Trapped: $_"
    continue                  # continue execution
    # break                  # stop execution (like throw)
}

# --- $LASTEXITCODE (native commands) ---
git status
if ($LASTEXITCODE -ne 0) {
    Write-Error "Git command failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

# --- Advanced error handling with -ErrorVariable ---
Get-ChildItem "*.log" -ErrorVariable errs -ErrorAction SilentlyContinue
if ($errs) {
    $errs | ForEach-Object { Write-Warning $_.Exception.Message }
}
"""),

    # ═══════════════════════════════════════════════════════════
    # POWERSHELL 5 — Functions & Advanced Functions
    # ═══════════════════════════════════════════════════════════
    ("powershell/functions-advanced.md", "powershell", ["pattern", "powershell"],
     "Functions & Advanced Functions",
     "function, param, [Parameter()], [CmdletBinding()], begin/process/end blocks.",
     "pattern",
     r"""# PowerShell functions and advanced functions

# --- Simple function ---
function Get-Greeting {
    param($Name)
    "Hello, $Name!"
}
Get-Greeting "Alice"

# --- Advanced function (cmdlet-like) ---
function Get-ProcessReport {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $false, Position = 0)]
        [string[]]$Name,

        [Parameter(ValueFromPipeline = $true)]
        [System.Diagnostics.Process]$InputObject,

        [ValidateSet("CPU", "Memory", "Disk")]
        [string]$SortBy = "CPU",

        [switch]$IncludeIdle
    )

    begin {
        Write-Verbose "Starting process report..."
        $results = [System.Collections.ArrayList]::new()
    }

    process {
        if ($InputObject) {
            $procs = @($InputObject)
        } elseif ($Name) {
            $procs = Get-Process -Name $Name -ErrorAction SilentlyContinue
        } else {
            $procs = Get-Process
        }

        foreach ($p in $procs) {
            if (-not $IncludeIdle -and $p.Id -eq 0) { continue }
            $null = $results.Add([PSCustomObject]@{
                ProcessName = $p.ProcessName
                Id          = $p.Id
                CPU_s       = [math]::Round($p.TotalProcessorTime.TotalSeconds, 2)
                MemMB       = [math]::Round($p.WorkingSet64 / 1MB, 2)
                StartTime   = $p.StartTime
            })
        }
    }

    end {
        switch ($SortBy) {
            "CPU"    { $results = $results | Sort-Object CPU_s -Descending }
            "Memory" { $results = $results | Sort-Object MemMB -Descending }
        }
        Write-Output $results
    }
}

# --- Usage ---
# Get-ProcessReport -Name "powershell*" -SortBy Memory -Verbose
# Get-Process | Get-ProcessReport -SortBy CPU
# Get-ProcessReport -IncludeIdle
"""),

    # ═══════════════════════════════════════════════════════════
    # POWERSHELL 6 — Remoting & CIM
    # ═══════════════════════════════════════════════════════════
    ("powershell/remoting-cim.md", "powershell", ["pattern", "powershell"],
     "Remoting & CIM",
     "Invoke-Command, Enter-PSSession, New-PSSession, Get-CimInstance, and WinRM configuration.",
     "pattern",
     r"""# PowerShell remoting and CIM/WMI

# --- One-off remote command ---
Invoke-Command -ComputerName SRV-APP01 -ScriptBlock {
    Get-Service | Where-Object Status -eq 'Running'
}

# --- Persistent session (PSSession) ---
$session = New-PSSession -ComputerName SRV-DB01, SRV-DB02 -Credential (Get-Credential)

# Run commands in both sessions
Invoke-Command -Session $session -ScriptBlock {
    Get-ChildItem D:\Databases
}

# Copy files to/from remote sessions
Copy-Item .\deploy.ps1 -Destination C:\Scripts\ -ToSession $session[0]
Copy-Item C:\Logs\app.log -Destination .\logs\ -FromSession $session[0]

# Remove session
Remove-PSSession $session

# --- Enter interactive session ---
# Enter-PSSession SRV-WEB01
# [SRV-WEB01]: PS C:\> Get-Service
# Exit-PSSession

# --- CIM (modern WMI) ---
Get-CimInstance -ClassName Win32_OperatingSystem
Get-CimInstance -ClassName Win32_ComputerSystem
Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DriveType=3"

# CIM session (reusable)
$cim = New-CimSession -ComputerName SRV-APP01
Get-CimInstance -CimSession $cim -ClassName Win32_Process |
    Where-Object { $_.WorkingSetSize -gt 100MB }
Remove-CimSession $cim

# --- WinRM configuration ---
# Enable PSRemoting (admin prompt)
# Enable-PSRemoting -Force

# Trusted hosts (for workgroup)
# Set-Item WSMan:\localhost\Client\TrustedHosts -Value "*.contoso.com" -Force

# Test connectivity
Test-WSMan SRV-APP01
Test-Connection SRV-APP01

# --- Fan-out pattern ---
$computers = Get-Content .\servers.txt
$jobs = $computers | ForEach-Object {
    Invoke-Command -ComputerName $_ -ScriptBlock {
        Get-WinEvent -LogName System -MaxEvents 100
    } -AsJob
}
$jobs | Receive-Job -Wait | Select-Object -First 50
"""),

    # ═══════════════════════════════════════════════════════════
    # POWERSHELL 7 — Active Directory & Users
    # ═══════════════════════════════════════════════════════════
    ("powershell/active-directory.md", "powershell", ["pattern", "powershell"],
     "Active Directory & Users",
     "Get-ADUser, New-ADUser, Set-ADUser, group management, computer objects, and AD module basics.",
     "pattern",
     r"""# Active Directory management with PowerShell

# --- Prerequisites ---
# Import-Module ActiveDirectory
# Or install RSAT: Add-WindowsCapability -Name Rsat.ActiveDirectory.DS-LDS.Tools~~~~0.0.1.0

# --- Query users ---
Get-ADUser -Identity jdoe
Get-ADUser -Filter {Enabled -eq $true} -Properties LastLogonDate, Department
Get-ADUser -Filter "Title -like '*Engineer*'" -SearchBase "OU=Engineering,DC=contoso,DC=com"

# --- Create a new user ---
New-ADUser -Name "John Doe" `
    -GivenName John `
    -Surname Doe `
    -SamAccountName jdoe `
    -UserPrincipalName jdoe@contoso.com `
    -Title "Software Engineer" `
    -Department Engineering `
    -Company Contoso `
    -Office "Building 4" `
    -StreetAddress "123 Main St" `
    -City "Seattle" `
    -State "WA" `
    -PostalCode "98101" `
    -Country US `
    -PhoneNumber "555-0100" `
    -MobilePhone "555-0199" `
    -AccountPassword (ConvertTo-SecureString "P@ssw0rd!" -AsPlainText -Force) `
    -Enabled $true `
    -PassThru

# --- Modify users ---
Set-ADUser jdoe -OfficePhone "555-0200" -Title "Senior Engineer"
Set-ADUser jdoe -Replace @{extensionAttribute1 = "Onboarding"}

# Disable / Enable
Disable-ADAccount -Identity jdoe
Enable-ADAccount -Identity jdoe

# --- Group management ---
# Create group
New-ADGroup -Name "Engineering-Admins" `
    -GroupScope Global `
    -GroupCategory Security `
    -Path "OU=Groups,DC=contoso,DC=com"

# Add/remove members
Add-ADGroupMember -Identity "Engineering-Admins" -Members jdoe, asmith
Remove-ADGroupMember -Identity "Engineering-Admins" -Members asmith -Confirm:$false

# Get group membership
Get-ADGroupMember -Identity "Domain Admins" | Select-Object Name, SamAccountName

# --- Computer objects ---
Get-ADComputer -Filter {OperatingSystem -like "*Server*"} -Properties OperatingSystem
Get-ADComputer -Identity SRV-APP01
Move-ADObject -Identity "CN=SRV-APP01,CN=Computers,DC=contoso,DC=com" `
    -TargetPath "OU=Servers,DC=contoso,DC=com"
"""),

    # ═══════════════════════════════════════════════════════════
    # POWERSHELL 8 — Logging & Transcripts
    # ═══════════════════════════════════════════════════════════
    ("powershell/logging-transcripts.md", "powershell", ["pattern", "powershell"],
     "Logging & Transcripts",
     "Start-Transcript, Write-Verbose/Debug/Information/Progress, structured logging, and transcript management.",
     "pattern",
     r"""# Logging and transcripts in PowerShell

# --- Transcript (full session log) ---
$transcriptPath = "C:\Logs\session-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"
Start-Transcript -Path $transcriptPath -Append
Write-Host "Session started at $(Get-Date)"
# ... run commands ...
Stop-Transcript

# --- Write-* stream output ---
Write-Verbose "Detailed verbose message" -Verbose         # -Verbose forces display
Write-Debug "Debug info for troubleshooting" -Debug       # -Debug forces display
Write-Information "Info message" -InformationAction Continue
Write-Warning "This is a warning"
Write-Error "This is a terminating error"

# --- Structured logging function ---
function Write-Log {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)]
        [string]$Message,

        [ValidateSet('INFO', 'WARN', 'ERROR', 'DEBUG')]
        [string]$Level = 'INFO',

        [string]$Component = 'General',

        [string]$LogFile = "C:\Logs\app.log"
    )

    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'
    $logEntry = "[$timestamp] [$Level] [$Component] $Message"

    # Console output
    switch ($Level) {
        'ERROR' { Write-Host $logEntry -ForegroundColor Red }
        'WARN'  { Write-Host $logEntry -ForegroundColor Yellow }
        'DEBUG' { Write-Host $logEntry -ForegroundColor Gray }
        default { Write-Host $logEntry -ForegroundColor Green }
    }

    # File output
    Add-Content -Path $LogFile -Value $logEntry
}

# Usage
Write-Log -Message "Deployment started" -Level INFO -Component Deploy
Write-Log -Message "Connection timeout" -Level WARN -Component Network
Write-Log -Message "Fatal exception" -Level ERROR -Component Core -LogFile "C:\Logs\errors.log"

# --- Write-Progress (long operations) ---
1..100 | ForEach-Object {
    Write-Progress -Activity "Processing files" `
        -Status "File $_ of 100" `
        -PercentComplete $_
    Start-Sleep -Milliseconds 50
}

# --- Advanced structured logging (JSON) ---
$logObject = [PSCustomObject]@{
    Timestamp   = (Get-Date -Format 'o')
    Level       = 'INFO'
    Component   = 'API'
    Message     = 'Request received'
    RequestId   = 'req-12345'
    Duration_ms = 42
}
$logObject | ConvertTo-Json -Compress | Add-Content -Path "C:\Logs\structured.log"
"""),

    # ═══════════════════════════════════════════════════════════
    # POWERSHELL 9 — WMI & System Management
    # ═══════════════════════════════════════════════════════════
    ("powershell/wmi-system.md", "powershell", ["pattern", "powershell"],
     "WMI & System Management",
     "Get-WmiObject, Win32_* classes, Get-Process, Get-Service, Stop-Service, Get-EventLog, and system inventory.",
     "pattern",
     r"""# WMI and system management

# --- WMI basics (Get-WmiObject) ---
# Note: Get-WmiObject is legacy; prefer Get-CimInstance where possible

# System information
Get-WmiObject Win32_OperatingSystem |
    Select-Object Caption, Version, BuildNumber, OSArchitecture, TotalVisibleMemorySize

Get-WmiObject Win32_ComputerSystem |
    Select-Object Manufacturer, Model, TotalPhysicalMemory, NumberOfProcessors

Get-WmiObject Win32_Processor |
    Select-Object Name, NumberOfCores, MaxClockSpeed, L2CacheSize, L3CacheSize

# Disk and storage
Get-WmiObject Win32_LogicalDisk -Filter "DriveType=3" |
    Select-Object DeviceID, @{N='SizeGB';E={[math]::Round($_.Size/1GB,2)}},
        @{N='FreeGB';E={[math]::Round($_.FreeSpace/1GB,2)}},
        @{N='PctFree';E={[math]::Round(($_.FreeSpace/$_.Size)*100,1)}}

# Network adapters
Get-WmiObject Win32_NetworkAdapterConfiguration |
    Where-Object { $_.IPEnabled -eq $true } |
    Select-Object Description, IPAddress, MACAddress, DefaultIPGateway, DNSServerSearchOrder

# --- Process management ---
Get-Process | Sort-Object CPU -Descending | Select-Object -First 10
Get-Process -Name "notepad" | Stop-Process -Force
Get-Process -Id $pid   # current PowerShell process

# --- Service management ---
Get-Service | Where-Object Status -eq 'Running'
Get-Service -Name "Spooler", "W3SVC"
Stop-Service -Name "Spooler" -Force
Set-Service -Name "W3SVC" -StartupType Automatic
Start-Service -Name "W3SVC"

# --- Event Log ---
Get-EventLog -LogName System -Newest 50 |
    Where-Object { $_.EntryType -eq 'Error' } |
    Select-Object TimeGenerated, Source, Message

# With WinRM:
# Get-WmiObject Win32_NTLogEvent -Filter "LogFile='System' AND Type='Error'" |
#     Select-Object -First 10 TimeGenerated, SourceName, Message

# --- Hardware inventory function ---
function Get-SystemInventory {
    [CmdletBinding()]
    param([string[]]$ComputerName = @($env:COMPUTERNAME))

    foreach ($comp in $ComputerName) {
        try {
            $os = Get-WmiObject Win32_OperatingSystem -ComputerName $comp
            $cs = Get-WmiObject Win32_ComputerSystem -ComputerName $comp
            $disk = Get-WmiObject Win32_LogicalDisk -ComputerName $comp -Filter "DriveType=3"

            [PSCustomObject]@{
                Computer     = $comp
                OS           = $os.Caption
                OSVersion    = $os.Version
                Manufacturer = $cs.Manufacturer
                Model        = $cs.Model
                RAM_GB       = [math]::Round($cs.TotalPhysicalMemory/1GB, 2)
                CPU          = $cs.NumberOfProcessors
                Disks        = ($disk | ForEach-Object {
                    "$($_.DeviceID) $([math]::Round($_.Size/1GB,0))GB"
                }) -join '; '
                LastBoot     = $os.LastBootUpTime
            }
        } catch {
            Write-Warning "Failed to query $comp : $_"
        }
    }
}
"""),

    # ═══════════════════════════════════════════════════════════
    # POWERSHELL 10 — REST API & JSON
    # ═══════════════════════════════════════════════════════════
    ("powershell/rest-api-json.md", "powershell", ["pattern", "powershell"],
     "REST API & JSON",
     "Invoke-RestMethod, Invoke-WebRequest, ConvertFrom-Json, handling headers, auth tokens, and pagination.",
     "pattern",
     r"""# REST API consumption and JSON handling

# --- Basic GET request ---
$response = Invoke-RestMethod -Uri "https://api.github.com/repos/PowerShell/PowerShell/releases" -Method Get
$response[0].tag_name
$response[0].assets | Select-Object name, size, browser_download_url

# --- POST with JSON body ---
$body = @{
    title       = "Bug report"
    body        = "Something broke"
    labels      = @("bug", "urgent")
} | ConvertTo-Json

$headers = @{
    "Content-Type" = "application/json"
}

$result = Invoke-RestMethod -Uri "https://api.github.com/repos/owner/repo/issues" `
    -Method Post `
    -Headers $headers `
    -Body $body

# --- Authentication (Bearer token) ---
$token = "ghp_your_token_here"
$authHeaders = @{
    Authorization = "Bearer $token"
    Accept        = "application/vnd.github.v3+json"
}

$user = Invoke-RestMethod -Uri "https://api.github.com/user" -Headers $authHeaders
Write-Host "Authenticated as $($user.login)"

# --- Invoke-WebRequest (raw response) ---
$webResponse = Invoke-WebRequest -Uri "https://api.github.com/repos/PowerShell/PowerShell"
$webResponse.StatusCode          # 200
$webResponse.Headers             # response headers
$webResponse.Content             # raw JSON string
$webResponse.Content | ConvertFrom-Json | Select-Object full_name, description

# --- Pagination (GitHub-style Link header) ---
function Get-GitHubIssues {
    param(
        [string]$Repo = "PowerShell/PowerShell",
        [string]$State = "open",
        [int]$PerPage = 100
    )

    $uri = "https://api.github.com/repos/$Repo/issues?state=$State&per_page=$PerPage&page=1"
    $allIssues = @()

    do {
        $response = Invoke-WebRequest -Uri $uri -Headers @{
            Accept = "application/vnd.github.v3+json"
        }
        $issues = $response.Content | ConvertFrom-Json
        $allIssues += $issues

        # Parse Link header for next page
        if ($response.Headers.Link) {
            $nextLink = $response.Headers.Link -match '<([^>]+)>;\s*rel="next"'
            $uri = if ($nextLink) { $matches[1] } else { $null }
        } else {
            $uri = $null
        }
    } while ($uri)

    return $allIssues
}

# --- POST with form data ---
$formData = @{
    grant_type    = "client_credentials"
    client_id     = "my-id"
    client_secret = "my-secret"
}

$tokenResponse = Invoke-RestMethod -Uri "https://auth.example.com/token" `
    -Method Post `
    -Body $formData

$accessToken = $tokenResponse.access_token

# --- Error handling with REST ---
try {
    $result = Invoke-RestMethod -Uri "https://api.example.com/data" `
        -ErrorAction Stop
}
catch [System.Net.WebException] {
    $statusCode = $_.Exception.Response.StatusCode.value__
    $errorBody  = $_.ErrorDetails.Message
    Write-Error "API error $statusCode : $errorBody"
}
catch {
    Write-Error "Request failed: $_"
}
"""),
]
