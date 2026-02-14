#!/bin/bash

# Add common install locations for uv to PATH
export PATH=$HOME/.local/bin:$HOME/.cargo/bin:$PATH

# Ensure we are in the script's directory
cd "$(dirname "$0")"

# detailed logging for debugging if it still fails
if ! command -v uv >/dev/null 2>&1; then
    echo "uv not found. Installing..." >&2
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Re-add to PATH in case it wasn't there before (redundant but safe)
    export PATH=$HOME/.local/bin:$HOME/.cargo/bin:$PATH
else
    echo "uv found at: $(command -v uv)" >&2
fi

# Ensure dependencies are installed
echo "Syncing dependencies..." >&2
uv sync --frozen

# Check for Playwright browsers (macOS specific check to save time)
# If the directory doesn't exist, we run the install.
# If it does, we assume they are installed to avoid the startup penalty.
PLAYWRIGHT_DIR="$HOME/Library/Caches/ms-playwright"
if [ ! -d "$PLAYWRIGHT_DIR" ]; then
    echo "Playwright browsers not found. Installing..." >&2
    uv run playwright install chromium
else
    echo "Playwright browsers found in $PLAYWRIGHT_DIR. Skipping install check." >&2
fi

echo "Starting Blinkit MCP..." >&2
exec uv run main.py
