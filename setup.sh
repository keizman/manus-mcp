#!/bin/bash
# Setup script for Manus MCP (Enhanced Edition)

set -e

echo "=== Manus MCP Setup ==="
echo ""

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "uv is not installed. Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Reload shell configuration
    if [ -f "$HOME/.bashrc" ]; then
        source "$HOME/.bashrc"
    elif [ -f "$HOME/.zshrc" ]; then
        source "$HOME/.zshrc"
    fi
else
    echo "✓ uv is already installed."
fi

# Create virtual environment
echo ""
echo "Creating virtual environment..."
uv venv

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Install dependencies
echo ""
echo "Installing core dependencies..."
uv pip install -e .

# Ask about legacy tools
echo ""
read -p "Install legacy local tools (browser-use, google search)? [y/N] " install_legacy
if [[ "$install_legacy" =~ ^[Yy]$ ]]; then
    echo "Installing legacy dependencies..."
    uv pip install -e ".[legacy]"
fi

# Ask about dev tools
echo ""
read -p "Install development dependencies (pytest, black, etc.)? [y/N] " install_dev
if [[ "$install_dev" =~ ^[Yy]$ ]]; then
    echo "Installing development dependencies..."
    uv pip install -e ".[dev]"
fi

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo ""
    echo "Creating .env file from template..."
    cp .env.example .env
    echo ""
    echo "⚠️  IMPORTANT: Edit .env and set your MANUS_API_KEY"
    echo "   Get your API key from: https://manus.im/settings"
fi

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Edit .env and set your MANUS_API_KEY"
echo "  2. Activate the virtual environment: source .venv/bin/activate"
echo "  3. Run the server: python mcp_server.py"
echo ""
echo "For Claude Desktop, add this to your config:"
echo '  {
    "mcpServers": {
      "manus-mcp": {
        "command": "uv",
        "args": ["--directory", "'$(pwd)'", "run", "mcp_server.py"],
        "env": {"MANUS_API_KEY": "your-key-here"}
      }
    }
  }'
echo ""
echo "For Codex CLI, run:"
echo "  codex --mcp-config claude_desktop_config.json"
