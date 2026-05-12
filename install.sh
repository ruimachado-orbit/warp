#!/usr/bin/env bash
# Warp Installation Script

set -e

AGENT_NAME="warp"
INSTALL_DIR="$HOME/.local/share/$AGENT_NAME"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/$AGENT_NAME"

echo "🚀 Installing Warp..."
echo ""

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
REQUIRED_VERSION="3.12"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "❌ Python $REQUIRED_VERSION or higher is required. Found: $PYTHON_VERSION"
    exit 1
fi

echo "✅ Python $PYTHON_VERSION detected"

# Create directories
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"
mkdir -p "$CONFIG_DIR"

# Copy files
echo "📦 Copying files..."
cp -r . "$INSTALL_DIR/"

# Create virtual environment
echo "🐍 Creating virtual environment..."
python3 -m venv "$INSTALL_DIR/.venv"

# Install dependencies
echo "📥 Installing dependencies..."
"$INSTALL_DIR/.venv/bin/pip" install -q --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

# Create wrapper script
cat > "$BIN_DIR/$AGENT_NAME" << EOF
#!/usr/bin/env bash
source "$INSTALL_DIR/.venv/bin/activate"
exec python3 "$INSTALL_DIR/bin/axsupport-cli" "\$@"
EOF

chmod +x "$BIN_DIR/$AGENT_NAME"

# Copy config examples
if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
    cp "$INSTALL_DIR/config/config.yaml.example" "$CONFIG_DIR/config.yaml"
    echo "✅ Created config file: $CONFIG_DIR/config.yaml"
fi

if [ ! -f "$CONFIG_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$CONFIG_DIR/.env"
    echo "✅ Created .env file: $CONFIG_DIR/.env"
fi

echo ""
echo "✨ Installation complete!"
echo ""
echo "📍 Installed to: $INSTALL_DIR"
echo "🔧 Config:      $CONFIG_DIR"
echo "🚀 Executable:  $BIN_DIR/$AGENT_NAME"
echo ""
echo "Next steps:"
echo "  1. Add $BIN_DIR to your PATH if not already:"
echo "     export PATH=\"\$HOME/.local/bin:\$PATH\""
echo "  2. Edit your config:"
echo "     $CONFIG_DIR/.env"
echo "     $CONFIG_DIR/config.yaml"
echo "  3. Run the agent:"
echo "     $AGENT_NAME chat"
echo ""
