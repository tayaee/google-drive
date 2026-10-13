#!/usr/bin/env bash
set -e

echo "=== Verifying issue-1: Browsing and navigating under 'Shared with me' ==="
uv run pytest tests/test_virtual_root.py
uv run pytest tests/test_dir_format.py
echo "[OK] All issue-1 verification tests passed successfully."
