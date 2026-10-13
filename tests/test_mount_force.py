import os
import pytest
from unittest.mock import patch
from google_drive.mount import (
    clear_mount_state,
    get_mount_state_file,
    is_pid_alive,
    save_mount_state,
    start_mount,
)


def test_is_pid_alive():
    # Current process must be alive
    assert is_pid_alive(os.getpid()) is True
    # Non-existent PID must be dead
    assert is_pid_alive(9999999) is False
    assert is_pid_alive(0) is False
    assert is_pid_alive(-1) is False


def test_mount_state_persistence(tmp_path):
    drive = "T:"
    save_mount_state(drive, 18875, 12345, "http://127.0.0.1:18875/")
    state_file = get_mount_state_file(drive)
    assert state_file.exists()

    clear_mount_state(drive)
    assert not state_file.exists()


def test_start_mount_aborts_when_already_running():
    drive = "T:"
    # Simulate an active process with current PID
    save_mount_state(drive, 18875, os.getpid(), "http://127.0.0.1:18875/")

    try:
        # Without force -> should abort (SystemExit 1)
        with pytest.raises(SystemExit) as exc:
            start_mount(drive_letter=drive, force=False)
        assert exc.value.code == 1
    finally:
        clear_mount_state(drive)
