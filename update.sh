#!/usr/bin/env bash
# =============================================================================
# update.sh  —  Build the FoE Best Buildings page and push to GitHub Pages
# =============================================================================
# Usage:
#   ./update.sh                        # uses all zips in exports/
#   ./update.sh path/to/CITY.zip ...   # explicit zip paths
#
# Requirements:
#   - Python 3.9+  (standard library only, no pip installs needed)
#   - git configured with push access to the repo
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "============================================"
echo "  FoE Best Buildings — Update Workflow"
echo "============================================"
echo ""

# ── 1. Run the builder ────────────────────────────────────────────────────────
if [ "$#" -gt 0 ]; then
    python3 build.py "$@"
else
    python3 build.py
fi

# ── 2. Confirm index.html was produced ───────────────────────────────────────
if [ ! -f "index.html" ]; then
    echo "ERROR: index.html was not created. Aborting."
    exit 1
fi

SIZE_KB=$(du -k index.html | cut -f1)
echo "  index.html confirmed: ${SIZE_KB} KB"
echo ""

# ── 3. Git commit and push ────────────────────────────────────────────────────
echo "Committing to git..."

git add index.html

# Only commit if there are actual changes
if git diff --cached --quiet; then
    echo "  No changes detected — index.html is already up to date."
    echo "  Nothing to push."
else
    BUILD_DATE=$(date -u "+%Y-%m-%d %H:%M UTC")
    git commit -m "Update best buildings — ${BUILD_DATE}"
    echo ""
    echo "Pushing to GitHub..."
    git push
    echo ""
    echo "============================================"
    echo "  Done! GitHub Pages will update shortly."
    echo "============================================"
fi

echo ""
