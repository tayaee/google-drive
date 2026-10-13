import socket
import pytest
from google_drive.mount import (
    find_available_port,
    is_port_available,
    normalize_drive_letter,
)


def test_is_port_available():
    port = find_available_port(18875)
    assert port >= 18875
    assert is_port_available(port)


def test_find_available_port_skips_occupied():
    start = find_available_port(18875)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", start))
        s.listen(1)

        next_port = find_available_port(start)
        assert next_port > start
        assert is_port_available(next_port)


def test_normalize_drive_letter():
    assert normalize_drive_letter(None) == "G:"
    assert normalize_drive_letter("") == "G:"
    assert normalize_drive_letter("g") == "G:"
    assert normalize_drive_letter("G") == "G:"
    assert normalize_drive_letter("G:") == "G:"
    assert normalize_drive_letter("Z:\\") == "Z:"

    with pytest.raises(ValueError):
        normalize_drive_letter("INVALID")
