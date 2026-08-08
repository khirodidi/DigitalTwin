# tests/conftest.py
# Shared pytest configuration — patches DB and MQTT so tests run without infra

import pytest
from unittest.mock import MagicMock, patch


# ── Patch PostgreSQL so no real DB is needed for unit tests ───────────────────
@pytest.fixture(autouse=True)
def mock_postgres(monkeypatch):
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: s
    mock_conn.cursor.return_value.__exit__  = MagicMock(return_value=False)
    mock_conn.cursor.return_value.fetchall  = MagicMock(return_value=[])
    mock_conn.cursor.return_value.fetchone  = MagicMock(return_value=(0,))
    mock_conn.autocommit = False

    monkeypatch.setattr(
        "persistence.postgres._conn", mock_conn
    )
    monkeypatch.setattr(
        "persistence.postgres.get_conn", lambda *a, **k: mock_conn
    )
    yield mock_conn
