"""Shared pytest fixtures."""

from __future__ import annotations

import contextlib
import os
import socket
import threading
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import pytest
from fastapi.testclient import TestClient

from taskboard12_api.main import create_app


def _libpq_url(url: str) -> str:
    """Normalise a SQLAlchemy-style URL (postgresql+psycopg2://) to a libpq URI."""
    parts = urlsplit(url)
    return urlunsplit(("postgresql", parts.netloc, parts.path, parts.query, parts.fragment))


def _with_host_port(url: str, host: str, port: int) -> str:
    parts = urlsplit(url)
    userinfo = parts.netloc.rpartition("@")[0]
    netloc = f"{userinfo}@{host}:{port}" if userinfo else f"{host}:{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """URL of a Postgres for the tests.

    TEST_DATABASE_URL when set, else a throwaway testcontainers Postgres. A missing
    Docker fails the requesting tests (it never skips them).
    """
    external = os.environ.get("TEST_DATABASE_URL")
    if external:
        yield _libpq_url(external)
        return
    from testcontainers.postgres import PostgresContainer  # imported here on purpose

    with PostgresContainer("postgres:16-alpine") as container:
        yield _libpq_url(container.get_connection_url())


@pytest.fixture()
def db_url(database_url: str) -> str:
    """The database URL with the tasks table dropped, so each test starts empty."""
    import psycopg

    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS tasks")
    return database_url


class DbProxy:
    """A TCP proxy in front of the test database that can refuse connections."""

    def __init__(self, target_host: str, target_port: int) -> None:
        self._target = (target_host, target_port)
        self._listener: socket.socket | None = None
        self._conns: list[socket.socket] = []
        self._lock = threading.Lock()
        self.port = 0
        self._hang = False

    def open(self) -> None:
        """Listen and forward to the database."""
        self._hang = False
        self._listen()

    def hang(self) -> None:
        """Listen and accept connections but never forward a byte."""
        self.close()
        self._hang = True
        self._listen()

    def _listen(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", self.port))
        listener.listen(16)
        self.port = listener.getsockname()[1]
        self._listener = listener
        threading.Thread(target=self._accept, args=(listener,), daemon=True).start()

    def close(self) -> None:
        listener, self._listener = self._listener, None
        if listener is not None:
            with contextlib.suppress(OSError):
                listener.shutdown(socket.SHUT_RDWR)  # wakes a thread blocked in accept()
            with contextlib.suppress(OSError):
                listener.close()
        with self._lock:
            conns, self._conns = self._conns, []
        for conn in conns:
            with contextlib.suppress(OSError):
                conn.shutdown(socket.SHUT_RDWR)
            with contextlib.suppress(OSError):
                conn.close()

    def _accept(self, listener: socket.socket) -> None:
        while True:
            try:
                client, _ = listener.accept()
            except OSError:
                return
            if self._hang:
                with self._lock:
                    self._conns.append(client)
                continue
            try:
                upstream = socket.create_connection(self._target, timeout=5)
            except OSError:
                client.close()
                continue
            with self._lock:
                self._conns += [client, upstream]
            for src, dst in ((client, upstream), (upstream, client)):
                threading.Thread(target=self._pump, args=(src, dst), daemon=True).start()

    @staticmethod
    def _pump(src: socket.socket, dst: socket.socket) -> None:
        try:
            while data := src.recv(65536):
                dst.sendall(data)
        except OSError:
            pass
        finally:
            for sock in (src, dst):
                with contextlib.suppress(OSError):
                    sock.shutdown(socket.SHUT_RDWR)
                with contextlib.suppress(OSError):
                    sock.close()


@pytest.fixture()
def db_proxy(db_url: str) -> Iterator[Any]:
    """Toggleable proxy: .open() forwards to the test database, .close() refuses.

    Exposes .url (database URL through the proxy). Starts open.
    """
    parts = urlsplit(db_url)
    assert parts.hostname is not None and parts.port is not None
    proxy = DbProxy(parts.hostname, parts.port)
    proxy.open()
    proxy.url = _with_host_port(db_url, "127.0.0.1", proxy.port)  # type: ignore[attr-defined]
    try:
        yield proxy
    finally:
        proxy.close()


@pytest.fixture()
def closed_port_url() -> str:
    """A database URL whose port nobody listens on (connection refused)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"postgresql://u:p@127.0.0.1:{port}/db"


@pytest.fixture()
def client(db_url: str) -> TestClient:
    """A TestClient for a database-backed application with an empty tasks table."""
    return TestClient(create_app(database_url=db_url))
