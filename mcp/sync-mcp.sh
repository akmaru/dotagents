#!/usr/bin/env bash
#
# sync-mcp.sh - Sync MCP configuration across all tools
#
# Usage:
#   1. Edit $XDG_CONFIG_HOME/mcp/master-mcp.json (master config)
#   2. Run ./sync-mcp.sh
#   3. Restart each tool
#
# Supported tools:
#   - Claude Code (user scope: ~/.claude.json)
#   - VS Code / GitHub Copilot (user scope: mcp.json)
#   - GitLab Duo (user scope: ~/.gitlab/duo/mcp.json)
#
set -euo pipefail

# ============================================================
# Configuration
# ============================================================

MASTER_CONFIG="${XDG_CONFIG_HOME}/mcp/master-mcp.json"

# Claude Code: mcpServers key in ~/.claude.json
CLAUDE_CODE_CONFIG="${HOME}/.claude.json"

# VS Code: user-level mcp.json
# macOS:  ~/Library/Application Support/Code/User/mcp.json
# Linux:  $XDG_CONFIG_HOME/Code/User/mcp.json
# Windows (WSL): adjust accordingly
if [[ "$(uname)" == "Darwin" ]]; then
    VSCODE_MCP_CONFIG="${HOME}/Library/Application Support/Code/User/mcp.json"
else
    VSCODE_MCP_CONFIG="${XDG_CONFIG_HOME}/Code/User/mcp.json"
fi

# GitLab Duo: ~/.gitlab/duo/mcp.json
GITLAB_DUO_CONFIG="${HOME}/.gitlab/duo/mcp.json"

# Claude Desktop: macOS only
# macOS:  ~/Library/Application Support/Claude/claude_desktop_config.json
if [[ "$(uname)" == "Darwin" ]]; then
    CLAUDE_DESKTOP_CONFIG="${HOME}/Library/Application Support/Claude/claude_desktop_config.json"
fi

# ============================================================
# Utilities
# ============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info()  { echo -e "${BLUE}[INFO]${NC}  $1" >&2; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $1" >&2; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1" >&2; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

check_jq() {
    if ! command -v jq &> /dev/null; then
        log_error "jq not found. Please install it:"
        echo "  macOS:  brew install jq"
        echo "  Ubuntu: sudo apt install jq"
        exit 1
    fi
}

backup_file() {
    local file="$1"
    if [[ -f "$file" ]]; then
        cp "$file" "${file}.bak.$(date +%Y%m%d_%H%M%S)"
        log_info "Backed up: ${file}.bak.*"
    fi
}

ensure_dir() {
    local dir
    dir=$(dirname "$1")
    mkdir -p "$dir"
}

# Get shell PATH by sourcing .zshrc/.bashrc
get_shell_path() {
    # Try to get PATH from shell config
    local shell_path=""

    # Try zsh first
    if [[ -f "${HOME}/.zshrc" ]]; then
        shell_path=$(zsh -c 'source ~/.zshrc 2>/dev/null; echo $PATH' 2>/dev/null)
    fi

    # Fallback to bash
    if [[ -z "$shell_path" ]] && [[ -f "${HOME}/.bashrc" ]]; then
        shell_path=$(bash -c 'source ~/.bashrc 2>/dev/null; echo $PATH' 2>/dev/null)
    fi

    # Fallback to current PATH
    if [[ -z "$shell_path" ]]; then
        shell_path="$PATH"
    fi

    echo "$shell_path"
}

# Resolve command path (e.g., "npx" -> "/Users/user/.local/share/mise/shims/npx")
resolve_command_path() {
    local cmd="$1"
    local shell_path="$2"

    # If already an absolute path, return as-is
    if [[ "$cmd" = /* ]]; then
        echo "$cmd"
        return
    fi

    # Try mise shims first (most common case)
    local mise_shim="${HOME}/.local/share/mise/shims/${cmd}"
    if [[ -x "$mise_shim" ]]; then
        echo "$mise_shim"
        return
    fi

    # Search in shell PATH
    local IFS=:
    for dir in $shell_path; do
        if [[ -x "${dir}/${cmd}" ]]; then
            echo "${dir}/${cmd}"
            return
        fi
    done

    # Not found, return original
    echo "$cmd"
}

# Enrich server configurations with resolved paths and PATH env
enrich_servers() {
    local servers_file="$1"
    local shell_path
    shell_path=$(get_shell_path)

    log_info "Enriching server configs (resolving paths, adding PATH)"

    local temp_input temp_output
    temp_input=$(mktemp)
    temp_output=$(mktemp)

    cat "$servers_file" > "$temp_input"

    # Process each server entry
    jq -c 'to_entries[]' "$temp_input" | while IFS= read -r server_entry; do
        local server_name server_data command resolved_cmd
        server_name=$(echo "$server_entry" | jq -r '.key')
        server_data=$(echo "$server_entry" | jq '.value')
        command=$(echo "$server_data" | jq -r '.command // empty')

        # Resolve command path if present
        if [[ -n "$command" ]]; then
            resolved_cmd=$(resolve_command_path "$command" "$shell_path")
            if [[ "$resolved_cmd" != "$command" ]]; then
                log_info "  $server_name: $command -> $resolved_cmd"
            fi
            server_data=$(echo "$server_data" | jq --arg cmd "$resolved_cmd" '.command = $cmd')

            # Add PATH to env. Only meaningful for stdio servers: HTTP/SSE servers are
            # reached over a URL and never spawn a process, so injecting env there would
            # add a key that has nothing to act on.
            server_data=$(echo "$server_data" | jq --arg path "$shell_path" '.env = ((.env // {}) + {"PATH": $path})')
        fi

        # Output updated server
        echo "$server_data" | jq -c --arg name "$server_name" '{($name): .}'
    done | jq -s 'add' > "$temp_output"

    cat "$temp_output"
    rm -f "$temp_input" "$temp_output"
}

# Extract and merge server definitions from master config and master-mcp.d/*.json
# Files in master-mcp.d/ are merged in alphabetical order, later files override earlier ones
get_servers() {
    local config_dir
    config_dir=$(dirname "$MASTER_CONFIG")
    local include_dir="${config_dir}/master-mcp.d"

    # Create temporary file for merging
    local temp_merged
    temp_merged=$(mktemp)

    # Start with master config
    jq 'del(.["$schema"], ._comment) | .servers | to_entries | map(.value |= del(._comment)) | from_entries' "$MASTER_CONFIG" > "$temp_merged"

    # Check if master-mcp.d directory exists
    if [[ -d "$include_dir" ]]; then
        # Merge configs from master-mcp.d/*.json (sorted order)
        local conf_count=0
        for conf in "$include_dir"/*.json; do
            if [[ -f "$conf" ]]; then
                log_info "Including: $(basename "$conf")"
                local temp_additional
                temp_additional=$(mktemp)

                if jq 'del(.["$schema"], ._comment) | .servers | to_entries | map(.value |= del(._comment)) | from_entries' "$conf" > "$temp_additional" 2>/dev/null; then
                    # Merge: additional servers completely override existing ones (not shallow merge)
                    # Use reduce to replace each server completely
                    local temp_result
                    temp_result=$(mktemp)
                    jq -s '
                        .[0] as $base |
                        .[1] as $override |
                        reduce ($override | keys[]) as $key (
                            $base;
                            .[$key] = $override[$key]
                        )
                    ' "$temp_merged" "$temp_additional" > "$temp_result"
                    mv "$temp_result" "$temp_merged"
                    rm -f "$temp_additional"
                    # Use arithmetic assignment, not ((conf_count++)): the latter
                    # returns exit 1 when the pre-increment value is 0, which trips
                    # `set -e` and aborts the script.
                    conf_count=$((conf_count + 1))
                else
                    log_warn "Skipping invalid JSON: $(basename "$conf")"
                    rm -f "$temp_additional"
                fi
            fi
        done

        if [[ $conf_count -gt 0 ]]; then
            log_info "Merged ${conf_count} additional config(s) from master-mcp.d/"
        fi
    fi

    # Output merged result
    cat "$temp_merged"
    rm -f "$temp_merged"
}

# ============================================================
# Claude Code
# ============================================================

sync_claude_code() {
    log_info "Syncing to Claude Code..."

    local servers_file enriched_file
    servers_file=$(mktemp)
    enriched_file=$(mktemp)

    get_servers > "$servers_file"
    enrich_servers "$servers_file" > "$enriched_file"

    ensure_dir "$CLAUDE_CODE_CONFIG"

    if [[ -f "$CLAUDE_CODE_CONFIG" ]]; then
        backup_file "$CLAUDE_CODE_CONFIG"
        # Merge mcpServers into existing .claude.json (preserves other keys)
        local tmp
        tmp=$(mktemp)
        jq --slurpfile servers "$enriched_file" '.mcpServers = $servers[0]' "$CLAUDE_CODE_CONFIG" > "$tmp"
        mv "$tmp" "$CLAUDE_CODE_CONFIG"
    else
        # Create new file
        jq -n --slurpfile servers "$enriched_file" '{"mcpServers": $servers[0]}' > "$CLAUDE_CODE_CONFIG"
    fi

    rm -f "$servers_file" "$enriched_file"
    log_ok "Claude Code: $CLAUDE_CODE_CONFIG"
}

# ============================================================
# VS Code / GitHub Copilot
# ============================================================

sync_vscode() {
    log_info "Syncing to VS Code (GitHub Copilot)..."

    local servers_file enriched_file
    servers_file=$(mktemp)
    enriched_file=$(mktemp)

    get_servers > "$servers_file"
    enrich_servers "$servers_file" > "$enriched_file"

    ensure_dir "$VSCODE_MCP_CONFIG"

    # VS Code uses the "servers" key (not "mcpServers")
    if [[ -f "$VSCODE_MCP_CONFIG" ]]; then
        backup_file "$VSCODE_MCP_CONFIG"
        local tmp
        tmp=$(mktemp)
        jq --slurpfile servers "$enriched_file" '.servers = $servers[0]' "$VSCODE_MCP_CONFIG" > "$tmp"
        mv "$tmp" "$VSCODE_MCP_CONFIG"
    else
        jq -n --slurpfile servers "$enriched_file" '{"servers": $servers[0]}' > "$VSCODE_MCP_CONFIG"
    fi

    rm -f "$servers_file" "$enriched_file"
    log_ok "VS Code:     $VSCODE_MCP_CONFIG"
}

# ============================================================
# GitLab Duo
# ============================================================

sync_gitlab_duo() {
    log_info "Syncing to GitLab Duo..."

    local servers_file enriched_file
    servers_file=$(mktemp)
    enriched_file=$(mktemp)

    get_servers > "$servers_file"
    enrich_servers "$servers_file" > "$enriched_file"

    ensure_dir "$GITLAB_DUO_CONFIG"
    backup_file "$GITLAB_DUO_CONFIG"

    # GitLab Duo uses the "mcpServers" key
    jq -n --slurpfile servers "$enriched_file" '{"mcpServers": $servers[0]}' > "$GITLAB_DUO_CONFIG"

    rm -f "$servers_file" "$enriched_file"
    log_ok "GitLab Duo:  $GITLAB_DUO_CONFIG"
}

# ============================================================
# Claude Desktop
# ============================================================

sync_claude_desktop() {
    if [[ -z "${CLAUDE_DESKTOP_CONFIG:-}" ]]; then
        log_warn "Claude Desktop sync is only supported on macOS"
        return 0
    fi

    log_info "Syncing to Claude Desktop..."

    local servers_file enriched_file
    servers_file=$(mktemp)
    enriched_file=$(mktemp)

    get_servers > "$servers_file"
    enrich_servers "$servers_file" > "$enriched_file"

    ensure_dir "$CLAUDE_DESKTOP_CONFIG"

    if [[ -f "$CLAUDE_DESKTOP_CONFIG" ]]; then
        backup_file "$CLAUDE_DESKTOP_CONFIG"
        # Merge mcpServers into existing config (preserves preferences and other keys)
        local tmp
        tmp=$(mktemp)
        jq --slurpfile servers "$enriched_file" '.mcpServers = $servers[0]' "$CLAUDE_DESKTOP_CONFIG" > "$tmp"
        mv "$tmp" "$CLAUDE_DESKTOP_CONFIG"
    else
        # Create new file
        jq -n --slurpfile servers "$enriched_file" '{"mcpServers": $servers[0]}' > "$CLAUDE_DESKTOP_CONFIG"
    fi

    rm -f "$servers_file" "$enriched_file"
    log_ok "Claude Desktop: $CLAUDE_DESKTOP_CONFIG"
}

# ============================================================
# Project-level sync (optional)
# ============================================================

sync_project() {
    local project_dir="$1"

    if [[ ! -d "$project_dir" ]]; then
        log_error "Directory does not exist: $project_dir"
        return 1
    fi

    log_info "Syncing project-level config: $project_dir"

    local servers_file enriched_file
    servers_file=$(mktemp)
    enriched_file=$(mktemp)

    get_servers > "$servers_file"
    enrich_servers "$servers_file" > "$enriched_file"

    # Claude Code: <project>/.mcp.json
    jq -n --slurpfile servers "$enriched_file" '{"mcpServers": $servers[0]}' \
        > "${project_dir}/.mcp.json"
    log_ok "  Claude Code:  ${project_dir}/.mcp.json"

    # VS Code: <project>/.vscode/mcp.json
    mkdir -p "${project_dir}/.vscode"
    jq -n --slurpfile servers "$enriched_file" '{"servers": $servers[0]}' \
        > "${project_dir}/.vscode/mcp.json"
    log_ok "  VS Code:      ${project_dir}/.vscode/mcp.json"

    # GitLab Duo: <project>/.gitlab/duo/mcp.json
    mkdir -p "${project_dir}/.gitlab/duo"
    jq -n --slurpfile servers "$enriched_file" '{"mcpServers": $servers[0]}' \
        > "${project_dir}/.gitlab/duo/mcp.json"
    log_ok "  GitLab Duo:   ${project_dir}/.gitlab/duo/mcp.json"

    rm -f "$servers_file" "$enriched_file"
}

# ============================================================
# Main
# ============================================================

main() {
    echo ""
    echo "========================================"
    echo "  MCP Config Sync Tool"
    echo "========================================"
    echo ""

    check_jq

    # Check master config exists
    if [[ ! -f "$MASTER_CONFIG" ]]; then
        log_error "Master config not found: $MASTER_CONFIG"
        log_info "First run: creating master config template"
        ensure_dir "$MASTER_CONFIG"
        cat > "$MASTER_CONFIG" << 'TEMPLATE'
{
  "_comment": "MCP master configuration - edit this file and run sync-mcp.sh to propagate",
  "servers": {
    "GitLab": {
      "type": "http",
      "url": "https://gitlab.com/api/v4/mcp"
    },
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    }
  }
}
TEMPLATE
        log_ok "Template created: $MASTER_CONFIG"
        log_info "Edit the config and run again"
        exit 0
    fi

    # Validate JSON
    if ! jq empty "$MASTER_CONFIG" 2>/dev/null; then
        log_error "Invalid JSON in master config: $MASTER_CONFIG"
        exit 1
    fi

    local server_count
    server_count=$(jq '.servers | length' "$MASTER_CONFIG")
    log_info "Master config: ${server_count} server(s) found"
    echo ""

    # User-level sync
    case "${1:-all}" in
        all)
            sync_claude_code
            sync_claude_desktop
            sync_vscode
            sync_gitlab_duo
            ;;
        claude)
            sync_claude_code
            ;;
        desktop)
            sync_claude_desktop
            ;;
        vscode)
            sync_vscode
            ;;
        gitlab)
            sync_gitlab_duo
            ;;
        project)
            if [[ -z "${2:-}" ]]; then
                log_error "Please specify a project path: $0 project /path/to/project"
                exit 1
            fi
            sync_project "$2"
            ;;
        *)
            echo "Usage: $0 [all|claude|desktop|vscode|gitlab|project <path>]"
            exit 1
            ;;
    esac

    echo ""
    log_ok "Sync complete! Restart each tool to apply changes."
    echo ""
    echo "  Verify with:"
    echo "    Claude Code:    claude mcp list"
    echo "    Claude Desktop: Settings > Developer > Edit Config"
    echo "    VS Code:        Command Palette > MCP: List Servers"
    echo "    GitLab Duo:     Command Palette > GitLab: Show MCP Dashboard"
    echo ""
}

main "$@"
