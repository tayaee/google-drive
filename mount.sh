#!/usr/bin/env bash
if command -v google-drive &> /dev/null; then
    google-drive mount "$@"
else
    uv run google-drive mount "$@"
fi
