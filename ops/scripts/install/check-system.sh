#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Hermes Cortex — System Verification Check
#  Run this BEFORE install.sh to verify your system is ready.
#
#  Usage:
#    ./check-system.sh              # Full check + recommendations
#    ./check-system.sh --json       # Machine-readable output
#    ./check-system.sh --minimal    # Pass/fail only
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── Config ──────────────────────────────────────────────────
HOME="${HOME:-$(echo ~)}"
VERSION="1.0.0"
CORTEX_PROFILE="${CORTEX_PROFILE:-server}"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

PASS=0; WARN=0; FAIL=0; INFO=0

pass() { PASS=$((PASS+1)); [[ "$1" != "quiet" ]] && printf "  ${GREEN}✅${RESET} %s\n" "$2"; }
warn() { WARN=$((WARN+1)); [[ "$1" != "quiet" ]] && printf "  ${YELLOW}⚠${RESET} %s\n" "$2"; }
fail() { FAIL=$((FAIL+1)); [[ "$1" != "quiet" ]] && printf "  ${RED}❌${RESET} %s\n" "$2"; }
info() { INFO=$((INFO+1)); [[ "$1" != "quiet" ]] && printf "  ${BLUE}ℹ${RESET}  %s\n" "$2"; }

header() { printf "\n${CYAN}${BOLD}━━━ %s ━━━${RESET}\n" "$1"; }
divider() { printf "  ${BOLD}%s${RESET}\n" "$1"; }

# ── JSON output mode ────────────────────────────────────────
MODE="${1:-normal}"  # normal, json, minimal
RESULTS_JSON='{"version":"'"$VERSION"'","checks":[],"recommendations":{},"summary":{"pass":0,"warn":0,"fail":0}}'

json_append() {
    local check="$1" status="$2" message="$3" detail="${4:-}"
    if [[ "$MODE" == "json" ]]; then
        RESULTS_JSON=$(echo "$RESULTS_JSON" | python3 -c "
import json, sys
data = json.load(sys.stdin)
data['checks'].append({
    'check': '$check',
    'status': '$status',
    'message': '$message',
    'detail': '$(echo "$detail" | sed "s/'//g")'
})
data['summary']['$status'] += 1
print(json.dumps(data, indent=2))
")
    fi
}

# ── Checks ──────────────────────────────────────────────────

check_os() {
    header "OPERATING SYSTEM"
    
    local os
    os=$(uname -s)
    
    if [[ "$os" == "Darwin" ]]; then
        local version sw_ver
        version=$(sw_vers -productVersion 2>/dev/null || echo "unknown")
        sw_ver=$(echo "$version" | cut -d. -f1)
        
        if [[ "$sw_ver" -ge 12 ]]; then
            pass "$MODE" "macOS $version (supported)"
            json_append "macos_version" "pass" "macOS $version" "Supported version detected"
        else
            warn "$MODE" "macOS $version — older than recommended (12+ required for some features)"
            json_append "macos_version" "warn" "macOS $version" "Older version, some features may not work"
        fi
        
        # Architecture
        local arch
        arch=$(uname -m)
        if [[ "$arch" == "arm64" ]]; then
            info "$MODE" "Apple Silicon ($arch) — full Metal GPU acceleration available"
            json_append "architecture" "info" "Apple Silicon" "Metal GPU acceleration for Ollama"
        else
            info "$MODE" "Intel Mac ($arch) — CPU-only inference, slower but works"
            json_append "architecture" "info" "Intel" "CPU-only, consider smaller models"
        fi
        
    elif [[ "$os" == "Linux" ]]; then
        warn "$MODE" "Linux detected — install.sh is optimized for macOS, but most steps work"
        json_append "os" "warn" "Linux" "macOS-optimized, some steps may need adaptation"
    else
        fail "$MODE" "Unsupported OS: $os (macOS or Linux required)"
        json_append "os" "fail" "Unsupported: $os" "Hermes Cortex requires macOS or Linux"
    fi
}

check_ram() {
    header "MEMORY"
    
    local total_ram ram_gb
    if [[ "$(uname)" == "Darwin" ]]; then
        total_ram=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
        ram_gb=$((total_ram / 1073741824))
    else
        total_ram=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}' || echo 0)
        ram_gb=$((total_ram / 1024 / 1024))
    fi
    
    if [[ $ram_gb -eq 0 ]]; then
        warn "$MODE" "Could not detect RAM size"
        json_append "ram" "warn" "Unknown RAM" "Could not detect"
        return
    fi
    
    info "$MODE" "${ram_gb} GB RAM detected"
    json_append "ram" "info" "${ram_gb} GB" "Detected system RAM"
    
    if [[ $ram_gb -ge 32 ]]; then
        pass "$MODE" "Excellent — can run large models (14B+) and full ZIM content"
        json_append "ram_tier" "pass" "Workstation tier" "32 GB+"
    elif [[ $ram_gb -ge 16 ]]; then
        pass "$MODE" "Good — can run 7-8B models and all ZIM bundles (~10 GB)"
        json_append "ram_tier" "pass" "Standard tier" "16 GB"
    elif [[ $ram_gb -ge 8 ]]; then
        pass "$MODE" "Adequate — run Qwen3:4b + travel bundle (~6 GB ZIM)"
        json_append "ram_tier" "pass" "Entry tier" "8 GB"
        warn "$MODE" "Limited headroom — close other apps during Ollama use"
        json_append "ram_headroom" "warn" "Limited RAM" "Close other apps"
    else
        fail "$MODE" "Less than 8 GB RAM — not recommended. Ollama + Docker will struggle."
        json_append "ram_tier" "fail" "Below minimum" "Under 8 GB"
    fi
}

check_disk() {
    header "DISK SPACE"
    
    local free_kb free_gb
    local check_path="${1:-$HOME}"
    
    if [[ "$(uname)" == "Darwin" ]]; then
        free_kb=$(df -k "$check_path" | awk 'NR==2 {print $4}')
    else
        free_kb=$(df -k "$check_path" | awk 'NR==2 {print $4}')
    fi
    
    free_gb=$((free_kb / 1024 / 1024))
    
    info "$MODE" "${free_gb} GB free on $(df -h "$check_path" | awk 'NR==2 {print $9}')"
    json_append "disk_free" "info" "${free_gb} GB free" "Available disk space"
    
    if [[ $free_gb -ge 50 ]]; then
        pass "$MODE" "Plenty of space — can fit everything including full Wikipedia"
        json_append "disk_tier" "pass" "50+ GB free" "All content fits"
    elif [[ $free_gb -ge 20 ]]; then
        pass "$MODE" "Good — fits all ZIM bundles (~10 GB) with room to spare"
        json_append "disk_tier" "pass" "20+ GB free" "All bundles fit"
    elif [[ $free_gb -ge 10 ]]; then
        pass "$MODE" "Adequate — fits essential bundles (~6 GB)"
        json_append "disk_tier" "pass" "10+ GB free" "Essential bundles fit"
        warn "$MODE" "Limited disk — won't fit large Wikipedia ZIMs"
        json_append "disk_headroom" "warn" "Limited disk" "No large ZIMs"
    else
        fail "$MODE" "Less than 10 GB free — need more space for offline content"
        json_append "disk_tier" "fail" "Under 10 GB" "Not enough space"
    fi
}

check_docker() {
    header "DOCKER"
    
    if command -v docker &>/dev/null; then
        local version
        version=$(docker --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+' | head -1 || echo "?")
        pass "$MODE" "Docker installed (v$version)"
        json_append "docker" "pass" "Docker v$version" ""
        
        # Check if Docker is running
        if docker ps &>/dev/null; then
            pass "$MODE" "Docker daemon running"
            json_append "docker_running" "pass" "Daemon running" ""
        else
            warn "$MODE" "Docker installed but not running — start Docker Desktop first"
            json_append "docker_running" "warn" "Not running" "Start Docker Desktop"
        fi
        
        # Check Docker VM memory
        if [[ "$(uname)" == "Darwin" ]] && command -v docker &>/dev/null; then
            local vm_mem
            vm_mem=$(docker info 2>/dev/null | grep -i "memory" | grep -oE '[0-9]+(\.[0-9]+)?Gi?B' | head -1 || echo "")
            if [[ -n "$vm_mem" ]]; then
                info "$MODE" "Docker VM memory: $vm_mem"
                json_append "docker_vm" "info" "VM: $vm_mem" ""
            fi
        fi
    elif [[ "$CORTEX_PROFILE" == "laptop" ]]; then
        info "$MODE" "Docker not installed (optional for laptop profile — kiwix needs it for ZIM viewer)"
        info "$MODE" "  Offline knowledge works without Docker (cascade falls through to mycortex + LLM)"
        json_append "docker" "info" "Not installed" "Optional for laptop"
    else
        warn "$MODE" "Docker not installed — required for kiwix-serve (ZIM content) and Langfuse"
        json_append "docker" "warn" "Not installed" "Required for ZIM server + Langfuse"
        info "$MODE" "  Install: https://docs.docker.com/desktop/install/mac-install/"
    fi
}

check_homebrew() {
    header "HOMEBREW"
    
    if command -v brew &>/dev/null; then
        local prefix
        prefix=$(brew --prefix 2>/dev/null || echo "?")
        pass "$MODE" "Homebrew installed ($prefix)"
        json_append "homebrew" "pass" "Installed at $prefix" ""
    else
        warn "$MODE" "Homebrew not installed — install.sh will attempt to install it"
        json_append "homebrew" "warn" "Not installed" "Will be installed by install.sh"
    fi
}

check_hermes() {
    header "HERMES AGENT"
    
    if command -v hermes &>/dev/null; then
        local version
        version=$(hermes --version 2>/dev/null || echo "installed")
        pass "$MODE" "Hermes Agent: $version"
        json_append "hermes" "pass" "$version" ""
    elif [[ -x "$HOME/.hermes/hermes-agent/venv/bin/hermes" ]]; then
        pass "$MODE" "Hermes Agent installed at ~/.hermes/hermes-agent/"
        json_append "hermes" "pass" "~/.hermes/" ""
    else
        warn "$MODE" "Hermes Agent not found — install.sh sets up everything else, but you'll need it"
        json_append "hermes" "warn" "Not found" "Install from https://hermes-agent.nousresearch.com/docs"
    fi
}

check_ollama() {
    header "OLLAMA"
    
    if command -v ollama &>/dev/null; then
        local version
        version=$(ollama --version 2>/dev/null || echo "installed")
        pass "$MODE" "Ollama: $version"
        json_append "ollama" "pass" "$version" ""
        
        # Check if running
        if curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
            pass "$MODE" "Ollama server running on 127.0.0.1:11434"
            json_append "ollama_running" "pass" "Running" ""
            
            # Check models
            local models
            models=$(ollama list 2>/dev/null | tail -n +2 || true)
            if [[ -n "$models" ]]; then
                info "$MODE" "Installed models:"
                json_append "ollama_models" "info" "Models found" ""
                while IFS= read -r line; do
                    [[ -z "$line" ]] && continue
                    printf "      · %s\n" "$line"
                done <<< "$models" || true
            else
                info "$MODE" "No models pulled yet (install.sh pulls nomic-embed-text)"
                json_append "ollama_models" "info" "No models" "Will be installed"
            fi
        else
            warn "$MODE" "Ollama installed but not running"
            json_append "ollama_running" "warn" "Not running" ""
        fi
    else
        info "$MODE" "Ollama not installed — install.sh will set it up"
        json_append "ollama" "info" "Not installed" "Will be installed"
    fi
}

check_network() {
    header "NETWORK"
    
    if ping -c 1 -t 3 8.8.8.8 &>/dev/null 2>&1; then
        pass "$MODE" "Internet connection available"
        json_append "network" "pass" "Connected" ""
    elif ping -c 1 -t 3 1.1.1.1 &>/dev/null 2>&1; then
        pass "$MODE" "Internet connection available"
        json_append "network" "pass" "Connected" ""
    else
        warn "$MODE" "No internet connection detected"
        json_append "network" "warn" "Offline" "Install will skip downloads"
        info "$MODE" "  System packages will still install, but content downloads will fail."
        info "$MODE" "  Run prep-offline.sh later when connected."
    fi
}

check_python() {
    header "PYTHON"
    
    if command -v python3 &>/dev/null; then
        local version
        version=$(python3 --version 2>/dev/null || echo "?")
        local py_ver
        py_ver=$(echo "$version" | grep -oE '[0-9]+\.[0-9]+' | head -1 || echo "0")
        
        if [[ $(echo "$py_ver" | cut -d. -f1) -ge 3 ]] && [[ $(echo "$py_ver" | cut -d. -f2) -ge 12 ]]; then
            pass "$MODE" "Python $version (3.12+ required)"
            json_append "python" "pass" "$version" ""
        else
            warn "$MODE" "Python $version — 3.12+ required (brew install python@3.12)"
            json_append "python" "warn" "$version" "3.12+ required"
        fi
    else
        fail "$MODE" "python3 not found — required for web cache, offline tools, scripts"
        json_append "python" "fail" "Not found" "Required"
    fi
}

check_git() {
    header "GIT"
    
    if command -v git &>/dev/null; then
        local version
        version=$(git --version 2>/dev/null || echo "?")
        pass "$MODE" "Git $version"
        json_append "git" "pass" "$version" ""
    else
        fail "$MODE" "git not found — required for cloning and brain sync"
        json_append "git" "fail" "Not found" "Required"
    fi
}

check_service_manager() {
    header "SERVICE MANAGEMENT"
    
    local os
    os=$(uname -s)
    
    # Define important cortex services (systemd unit names / launchd labels)
    local -a SERVICES=()
    local -a SERVICE_NAMES=()
    
    if [[ "$os" == "Darwin" ]]; then
        # macOS: launchd labels
        SERVICES=(
            "com.ollama.serve"
            "com.hermes.gateway"
            "com.hermes.cortex-dashboard"
        )
        SERVICE_NAMES=(
            "Ollama"
            "Hermes Gateway"
            "Cortex Dashboard"
        )
        local svc_mgr="launchd"
    elif [[ "$os" == "Linux" ]]; then
        # Linux: systemd user service names
        SERVICES=(
            "ollama"
            "hermes-gateway"
            "hermes-cortex-dashboard"
        )
        SERVICE_NAMES=(
            "Ollama"
            "Hermes Gateway"
            "Cortex Dashboard"
        )
        local svc_mgr="systemd"
    else
        info "$MODE" "Unknown OS — cannot check service manager"
        json_append "service_manager" "info" "Unknown OS" ""
        return
    fi
    
    local managed=0 unmanaged_found=0 not_installed=0
    
    for i in "${!SERVICES[@]}"; do
        local label="${SERVICES[$i]}"
        local display="${SERVICE_NAMES[$i]}"
        
        if [[ "$os" == "Darwin" ]]; then
            # Check if launchd service exists
            local plist_path="$HOME/Library/LaunchAgents/${label}.plist"
            if launchctl list "$label" &>/dev/null 2>&1; then
                local pid
                pid=$(launchctl list "$label" 2>/dev/null | awk '{print $1}' | grep -v '^\s*$')
                if [[ -n "$pid" && "$pid" != "-" ]]; then
                    pass "$MODE" "launchd: $display (PID $pid)"
                else
                    warn "$MODE" "launchd: $display (registered, not running)"
                fi
                managed=$((managed + 1))
            elif [[ -f "$plist_path" ]]; then
                info "$MODE" "launchd: $display (plist exists, not loaded)"
                managed=$((managed + 1))
            else
                info "$MODE" "launchd: $display (not yet installed)"
                not_installed=$((not_installed + 1))
            fi
        else
            # Linux: Check systemd user service
            local unit_dir="$HOME/.config/systemd/user"
            local unit_file="${unit_dir}/${label}.service"
            
            if systemctl --user is-active --quiet "$label" 2>/dev/null; then
                local enabled_status
                enabled_status=$(systemctl --user is-enabled "$label" 2>/dev/null || echo "?")
                pass "$MODE" "systemd: $display (active, $enabled_status)"
                managed=$((managed + 1))
            elif systemctl --user is-enabled --quiet "$label" 2>/dev/null; then
                warn "$MODE" "systemd: $display (enabled but not active)"
                managed=$((managed + 1))
            elif [[ -f "$unit_file" ]]; then
                info "$MODE" "systemd: $display (unit exists, not enabled)"
                managed=$((managed + 1))
            else
                info "$MODE" "systemd: $display (not yet installed)"
                not_installed=$((not_installed + 1))
            fi
        fi
    done
    
    # Detect unmanaged processes — running without systemd/launchd
    if [[ "$os" == "Linux" ]]; then
        local ollama_pid hermes_pid
        # Check for unmanaged Ollama process (running outside systemd)
        ollama_pid=$(pgrep -f "ollama serve" 2>/dev/null || true)
        hermes_pid=$(pgrep -f "hermes_cli.main" 2>/dev/null || true)
        
        if [[ -n "$ollama_pid" ]]; then
            # Check if it's NOT the systemd-managed service
            if ! systemctl --user is-active --quiet ollama 2>/dev/null; then
                warn "$MODE" "⚠ Ollama running (PID $ollama_pid) but NOT managed by systemd — no auto-restart, will not survive reboot"
                unmanaged_found=$((unmanaged_found + 1))
            fi
        fi
        if [[ -n "$hermes_pid" ]]; then
            if ! systemctl --user is-active --quiet hermes-gateway 2>/dev/null; then
                warn "$MODE" "⚠ Hermes Gateway running (PID $hermes_pid) but NOT managed by systemd — no auto-restart"
                unmanaged_found=$((unmanaged_found + 1))
            fi
        fi
    elif [[ "$os" == "Darwin" ]]; then
        local ollama_pid hermes_pid
        ollama_pid=$(pgrep -x ollama 2>/dev/null || true)
        hermes_pid=$(pgrep -f "hermes.*gateway" 2>/dev/null || true)
        
        if [[ -n "$ollama_pid" ]]; then
            if ! launchctl list com.ollama.serve &>/dev/null 2>&1; then
                warn "$MODE" "⚠ Ollama running (PID $ollama_pid) but NOT managed by launchd"
                unmanaged_found=$((unmanaged_found + 1))
            fi
        fi
        if [[ -n "$hermes_pid" ]]; then
            if ! launchctl list com.hermes.gateway &>/dev/null 2>&1; then
                warn "$MODE" "⚠ Hermes Gateway running (PID $hermes_pid) but NOT managed by launchd"
                unmanaged_found=$((unmanaged_found + 1))
            fi
        fi
    fi
    
    # Summary
    local summary="$managed managed service(s)"
    if [[ $not_installed -gt 0 ]]; then
        summary="$summary, $not_installed not yet installed"
    fi
    if [[ $unmanaged_found -gt 0 ]]; then
        fail "$MODE" "$summary, $unmanaged_found running UNMANAGED — use install.sh to set up service files"
        json_append "service_manager" "fail" "$summary" "Unmanaged processes detected"
    else
        pass "$MODE" "$summary — all services properly managed by $svc_mgr"
        json_append "service_manager" "pass" "$summary" "All services managed"
    fi
}

# ── Recommendations ─────────────────────────────────────────

print_recommendations() {
    header "RECOMMENDATIONS"
    
    # Determine RAM tier
    local ram_gb=0
    if [[ "$(uname)" == "Darwin" ]]; then
        ram_gb=$(($(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824))
    fi
    
    local free_gb=0
    free_gb=$(df -k "$HOME" | awk 'NR==2 {print $4}' 2>/dev/null)
    free_gb=$((free_gb / 1024 / 1024))
    
    divider "Model Recommendation"
    if [[ $ram_gb -ge 64 ]]; then
        info "$MODE" "Ollama model: Qwen3:32b or Llama3.3:70b"
    elif [[ $ram_gb -ge 32 ]]; then
        info "$MODE" "Ollama model: Qwen3:14b or DeepSeek-Coder:14b"
    elif [[ $ram_gb -ge 16 ]]; then
        info "$MODE" "Ollama model: Qwen3:8b or DeepSeek-R1:7b"
    elif [[ $ram_gb -ge 8 ]]; then
        info "$MODE" "Ollama model: Qwen3:4b or Gemma3:1b"
    else
        info "$MODE" "RAM too low for comfortable Ollama usage"
    fi
    
    divider "Offline Content"
    if [[ $free_gb -ge 20 ]]; then
        info "$MODE" "ZIM bundle: All bundles (~10 GB) + Wikipedia mini (~12 GB)"
    elif [[ $free_gb -ge 10 ]]; then
        info "$MODE" "ZIM bundle: All bundles (~10 GB)"
    else
        info "$MODE" "ZIM bundle: Travel (~6 GB) or Education (~5 GB)"
    fi
    
    # Check if ZIM content exists
    if [[ -d "$HOME/offline/zim" ]] && ls "$HOME/offline/zim"/*.zim &>/dev/null 2>&1; then
        local zim_count zim_size
        zim_count=$(ls "$HOME/offline/zim"/*.zim 2>/dev/null | wc -l | tr -d ' ')
        zim_size=$(du -sh "$HOME/offline/zim" 2>/dev/null | cut -f1)
        info "$MODE" "ZIM content already: $zim_count files ($zim_size)"
        info "$MODE" "  Run prep-offline to add more."
    else
        info "$MODE" "No ZIM content yet. After install, run:"
        info "$MODE" "  prep-offline --mode=travel   (jungle/vacation, ~6 GB)"
        info "$MODE" "  prep-offline --mode=build    (offline dev, ~7 GB)"
        info "$MODE" "  prep-offline --mode=education (kid learning, ~5 GB)"
    fi
    
    divider "Quick Reference"
    info "$MODE" "System specs saved to: docs/computer-specs.md"
}

# ── Summary ─────────────────────────────────────────────────

print_summary() {
    header "SUMMARY"
    
    local total=$((PASS + WARN + FAIL))
    printf "\n"
    printf "  ${GREEN}${BOLD}%d passed${RESET}  ${YELLOW}${BOLD}%d warnings${RESET}  ${RED}${BOLD}%d failures${RESET}  (%d total checks)\n\n" "$PASS" "$WARN" "$FAIL" "$total"
    
    if [[ $FAIL -gt 0 ]]; then
        printf "  ${RED}${BOLD}❌ Some checks failed.${RESET} Review the items above before installing.\n\n"
    elif [[ $WARN -gt 0 ]]; then
        printf "  ${YELLOW}${BOLD}⚠  All essential checks passed, but review warnings.${RESET}\n\n"
    else
        printf "  ${GREEN}${BOLD}✅ Everything looks good. Ready to install!${RESET}\n\n"
    fi
}

# ── Main ────────────────────────────────────────────────────

main() {
    echo ""
    echo "  ╔══════════════════════════════════════════════════════╗"
    echo "  ║     Hermes Cortex — System Verification v${VERSION}       ║"
    echo "  ║     Profile: ${CORTEX_PROFILE}                           ║"
    echo "  ║     Run this before install.sh to check readiness     ║"
    echo "  ╚══════════════════════════════════════════════════════╝"
    
    check_os
    check_ram
    check_disk
    check_python
    check_git
    check_network
    check_homebrew
    check_docker
    check_hermes
    check_ollama
    check_service_manager
    
    print_recommendations
    print_summary
    
    # Exit code: 0 if no failures, 1 if any failures
    if [[ $FAIL -gt 0 ]]; then
        exit 1
    fi
}

main "$@"
