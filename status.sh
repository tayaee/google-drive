#!/usr/bin/env bash
if command -v google-drive &> /dev/null; then
    google-drive status "$@"
else
    uv run google-drive status "$@"
fi
