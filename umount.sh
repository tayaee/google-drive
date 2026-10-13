#!/usr/bin/env bash
if command -v google-drive &> /dev/null; then
    google-drive umount "$@"
else
    uv run google-drive umount "$@"
fi
