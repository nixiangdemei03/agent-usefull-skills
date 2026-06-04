#!/usr/bin/env bash
# SMS MCP Server — Installer
# Installs dependencies and configures Claude Code to use it.
#
# Usage:
#   chmod +x install.sh && ./install.sh
#   ./install.sh --dir /path/to/memory      # custom memory directory
#   ./install.sh --uninstall                # remove config
#
# After install, restart Claude Code.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_CONFIG="${CLAUDE_CONFIG:-$HOME/Library/Application Support/Claude/claude_desktop_config.json}"
VSC_CLAUDE_CONFIG="$HOME/.vscode-server/data/claude.json"

# Colours
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   SMS MCP Server — Installer         ║${NC}"
echo -e "${CYAN}║   Smart Memory System ↔ Claude Code   ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
echo ""

# ── Parse args ──────────────────────────────────────────────

MEMORY_DIR=""
UNINSTALL=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) MEMORY_DIR="$2"; shift 2 ;;
    --uninstall) UNINSTALL=true; shift ;;
    *) echo -e "${RED}Unknown: $1${NC}"; exit 1 ;;
  esac
done

if [[ -z "$MEMORY_DIR" ]]; then
  # Default: look for memory/ near the script, or ask the user
  if [[ -d "$SCRIPT_DIR/../memory" ]]; then
    MEMORY_DIR="$(cd "$SCRIPT_DIR/../memory" && pwd)"
  else
    echo -e "${YELLOW}No --dir provided and no memory/ found.${NC}"
    echo -e "Enter the path to your SMS memory directory (or leave empty for default):"
    read -r INPUT_DIR
    if [[ -n "$INPUT_DIR" ]]; then
      MEMORY_DIR="$(realpath "$INPUT_DIR" 2>/dev/null || echo "$INPUT_DIR")"
    else
      MEMORY_DIR="$(pwd)/memory"
      echo -e "${YELLOW}Defaulting to: $MEMORY_DIR${NC}"
    fi
  fi
fi

echo -e "${GREEN}📁 Memory directory: $MEMORY_DIR${NC}"
echo ""
echo -e "${CYAN}📋 Initializing blank SMS memory...${NC}"

# Create directory structure
mkdir -p "$MEMORY_DIR/auto/raw"
mkdir -p "$MEMORY_DIR/curated"
mkdir -p "$MEMORY_DIR/cache"

# Create empty consolidated template
cat > "$MEMORY_DIR/curated/consolidated.json" << SMSEOF
{
  "schema_version": "3.0",
  "type": "consolidated",
  "description": "Smart Memory System — 你的记忆将从这里开始。安装后首次 compress 会自动填充。",
  "priority": 1,
  "total_consolidated": 0,
  "entries": []
}
SMSEOF

# Create empty cache
cat > "$MEMORY_DIR/cache/memory_cache.json" << SMSEOF
{
  "schema_version": "3.0",
  "hot_tier": {"count": 0, "max": 20, "entries": []},
  "stats": {"total_entries": 0}
}
SMSEOF

echo -e "   ${GREEN}✅ Blank memory structure created at:${NC}"
echo -e "      $MEMORY_DIR"
echo -e "      ├─ auto/raw/     ← 全量日志"
echo -e "      ├─ curated/     ← 最高优先级 consolidated"
echo -e "      └─ cache/       ← Hot 层缓存"
echo ""
# ── Generate CLAUDE.md (auto memory rules) ──────────────────
CLAUDE_FILE="${CLAUDE_PATH:-$HOME/CLAUDE.md}"
if [ ! -f "$CLAUDE_FILE" ]; then
  cat > "$CLAUDE_FILE" << 'CLAUDE'
# SMS — Auto Memory Rules

sms-v3 version \`sms-v3-mcp\` connected.
> DO NOT wait for the user to say "remember this". Record automatically.

---

## Decision Tree: Should I remember this?

### Q1: Did I learn something new?
Command, API, config, concept, workflow → type=knowledge

### Q2: Did the user reveal a preference?
Liking/disliking, habits, working style → type=preference

### Q3: Did we make a decision?
Chose A over B with a reason → type=decision (include WHY in detail)

### Q4: Did we fix something?
Solved an error or bug → type=failure (record SOLUTION, not error text)

### Q5: Did we finish something?
Task with concrete outcome → type=event

### Q6: Did I notice a pattern across sessions?
Same thing happened 3+ times → type=insight

### Q7: User said "remember this"?
Figure out the type and record it.

## What NOT to record
- Greetings: hi, hello, good morning
- Acknowledgments: ok, got it, thanks
- Status: let me check, let me try
- Unresolved discussions: no conclusion
- Duplicates: already merged via fingerprint
- Raw error text: record the fix, not the symptom

## Search Rules
User asks about past → search_fts() before answering
Try 2-3 related keywords if first returns nothing
If found → reference it AND call hit_memory()

## Tagging Guide
Good: ["ssh","cse","unsw"]  Bad: ["learned","stuff","note"]
CLAUDE

  if command -v cygpath &>/dev/null || [ -d "/mnt/c" ]; then
    # Windows/WSL detected — also write to Windows home
    WIN_HOME=$(wslpath "$(wslvar USERPROFILE 2>/dev/null)" 2>/dev/null || echo "")
    if [ -n "$WIN_HOME" ] && [ ! -f "$WIN_HOME/CLAUDE.md" ]; then
      cp "$CLAUDE_FILE" "$WIN_HOME/CLAUDE.md"
      echo -e "   ${GREEN}✅ Also wrote to Windows: $WIN_HOME\\CLAUDE.md${NC}"
    fi
  fi

  echo -e "   ${GREEN}✅ CLAUDE.md auto-rules created at:${NC}"
  echo -e "      $CLAUDE_FILE"
else
  echo -e "   ${YELLOW}⚠️  CLAUDE.md already exists at $CLAUDE_FILE, skipping...${NC}"
fi
echo ""
# ── Install dependencies ────────────────────────────────────

if ! command -v node &>/dev/null; then
  echo -e "${RED}❌ Node.js is required. Install it first: https://nodejs.org${NC}"
  exit 1
fi

echo -e "${CYAN}📦 Installing dependencies...${NC}"
cd "$SCRIPT_DIR"
npm install --silent 2>&1 | tail -1
echo -e "${GREEN}✅ Dependencies installed${NC}"

# ── Make server executable ──────────────────────────────────

chmod +x "$SCRIPT_DIR/server.js"

# ── Build MCP config block ──────────────────────────────────

MCP_CONFIG_BLOCK=$(cat <<EOF
{
  "sms-mcp": {
    "command": "node",
    "args": ["$SCRIPT_DIR/server.js", "--dir", "$MEMORY_DIR"],
    "env": {},
    "disabled": false,
    "autoApprove": []
  }
}
EOF
)

# ── Uninstall ───────────────────────────────────────────────

if $UNINSTALL; then
  echo -e "${YELLOW}🧹 Uninstalling...${NC}"

  if [[ -f "$CLAUDE_CONFIG" ]]; then
    tmp=$(mktemp)
    jq 'del(."mcpServers"."sms-mcp")' "$CLAUDE_CONFIG" > "$tmp" && mv "$tmp" "$CLAUDE_CONFIG"
    echo -e "${GREEN}✅ Removed from Claude Desktop config${NC}"
  fi

  if [[ -f "$VSC_CLAUDE_CONFIG" ]]; then
    tmp=$(mktemp)
    jq 'del(."mcpServers"."sms-mcp")' "$VSC_CLAUDE_CONFIG" > "$tmp" && mv "$tmp" "$VSC_CLAUDE_CONFIG"
    echo -e "${GREEN}✅ Removed from VS Code Claude config${NC}"
  fi

  echo -e "${GREEN}✅ Uninstall complete${NC}"
  exit 0
fi

# ── Install to Claude Desktop ───────────────────────────────

if [[ -f "$CLAUDE_CONFIG" ]]; then
  echo -e "${CYAN}🔧 Configuring Claude Desktop...${NC}"
  tmp=$(mktemp)
  jq --argjson mcp "$MCP_CONFIG_BLOCK" \
    '.mcpServers = (.mcpServers // {}) + $mcp' \
    "$CLAUDE_CONFIG" > "$tmp" && mv "$tmp" "$CLAUDE_CONFIG"
  echo -e "${GREEN}✅ Updated: $CLAUDE_CONFIG${NC}"
else
  echo -e "${YELLOW}⚠️  Claude Desktop config not found at:${NC}"
  echo -e "   $CLAUDE_CONFIG"
  echo -e "   Create it manually with this content:"
  echo ""
  echo -e "${CYAN}{${NC}"
  echo -e "${CYAN}  \"mcpServers\": $MCP_CONFIG_BLOCK${NC}"
  echo -e "${CYAN}}${NC}"
  echo ""
fi

# ── Install to VS Code Claude ───────────────────────────────

if [[ -f "$VSC_CLAUDE_CONFIG" ]]; then
  echo -e "${CYAN}🔧 Configuring VS Code Claude Extension...${NC}"
  tmp=$(mktemp)
  jq --argjson mcp "$MCP_CONFIG_BLOCK" \
    '.mcpServers = (.mcpServers // {}) + $mcp' \
    "$VSC_CLAUDE_CONFIG" > "$tmp" && mv "$tmp" "$VSC_CLAUDE_CONFIG"
  echo -e "${GREEN}✅ Updated: $VSC_CLAUDE_CONFIG${NC}"
fi

# ── Summary ─────────────────────────────────────────────────

echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   ✅ Installation Complete!          ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""
echo -e "   ${CYAN}Server:${NC}     $SCRIPT_DIR/server.js"
echo -e "   ${CYAN}Memory:${NC}     $MEMORY_DIR"
echo -e "   ${CYAN}Config:${NC}     sms-mcp"
echo ""
echo -e "   ${YELLOW}Next steps:${NC}"
echo -e "   1. Restart Claude Desktop / Claude Code"
echo -e "   2. Try:  ${CYAN}List available MCP tools${NC}"
echo -e "   3. Try:  ${CYAN}Read sms://cache${NC}"
echo -e "   4. Try:  ${CYAN}Search my memories for 'regex'${NC}"
echo ""
echo -e "   ${GREEN}✨ SMS is now accessible from Claude!${NC}"
