---
language: nix
tags: [pattern, nix]
title: Home Manager
description: home.nix configuration: programs, services, home.packages, home.file, and nixpkgs.config.
source: pattern
---

```nix
# home.nix — Home Manager configuration
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

```
