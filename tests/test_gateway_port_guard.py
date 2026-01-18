#!/usr/bin/env python3
"""Test gateway port collision detection."""
import socket
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from scripts.start_chat_gateway import check_port_available


def test_port_available_when_free():
    """Test that check_port_available returns True for an available port."""
    # Use a high port number that's unlikely to be in use
    assert check_port_available("127.0.0.1", 59999)


def test_port_unavailable_when_bound():
    """Test that check_port_available returns False for a bound port."""
    # Bind to a port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 59998))
    sock.listen(1)
    
    try:
        # Check should return False since port is bound
        assert not check_port_available("127.0.0.1", 59998)
    finally:
        sock.close()


def test_port_available_after_release():
    """Test that port becomes available after release."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 59997))
    sock.listen(1)
    sock.close()
    
    # Port should be available now
    assert check_port_available("127.0.0.1", 59997)
