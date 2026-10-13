#!/usr/bin/env bash
set -e

echo "============================================================"
echo "  Google Drive CLI Tool Installer (uv tool)"
echo "============================================================"

if ! command -v uv &> /dev/null; then
    echo "[!] Error: 'uv' is not installed or not in your PATH."
    echo "Please install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo "[*] Installing google-drive as uv tool..."
uv tool install --force --reinstall .

echo ""
echo "============================================================"
echo "[SUCCESS] google-drive has been installed!"
echo "============================================================"
echo "Available commands:"
echo "  google-drive status"
echo "  google-drive mount"
echo "  google-drive umount"
echo "  google-drive dir"
echo "============================================================"
