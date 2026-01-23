#!/usr/bin/env python3
"""Test gateway port collision detection."""
import socket
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from scripts.start_chat_gateway import check_port_available


def _get_ephemeral_port() -> int:
    """Get an ephemeral port that is currently free."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def test_port_available_when_free():
    """Test that check_port_available returns True for an available port."""
    # Get an ephemeral port that was just released
    port = _get_ephemeral_port()
    assert check_port_available("127.0.0.1", port)


def test_port_unavailable_when_bound():
    """Test that check_port_available returns False for a bound port."""
    # Bind to an ephemeral port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    bound_port = sock.getsockname()[1]
    sock.listen(1)

    try:
        # Check should return False since port is bound
        assert not check_port_available("127.0.0.1", bound_port)
    finally:
        sock.close()


def test_port_available_after_release():
    """Test that port becomes available after release."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    bound_port = sock.getsockname()[1]
    sock.listen(1)
    sock.close()

    # Port should be available now (with SO_REUSEADDR, this should work reliably)
    assert check_port_available("127.0.0.1", bound_port)
