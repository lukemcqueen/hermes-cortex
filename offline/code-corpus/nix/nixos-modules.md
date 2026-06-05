---
language: nix
tags: [pattern, nix]
title: NixOS Modules
description: Module system: imports, options, config, mkIf, mkMerge, types, and conditional configuration.
source: pattern
---

```nix
# NixOS module — declarative system configuration
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

```
