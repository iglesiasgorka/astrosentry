"""Unit tests must never contact external services."""

import socket

import pytest


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    """Fail immediately if a unit test tries to resolve or connect to a host."""
    def deny(*args, **kwargs):
        raise AssertionError("Network access is forbidden in unit tests.")
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
