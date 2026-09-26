"""Shared pytest fixtures: an isolated database per test."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.insert(0, str(ROOT))

os.environ.setdefault("MUSTACOM_DATA_DIR", str(ROOT / ".pytest-data"))

from mustacom.config import build_paths  # noqa: E402
from mustacom.db.database import open_database  # noqa: E402
from mustacom.services import Services  # noqa: E402


@pytest.fixture
def db(tmp_path):
    database = open_database(tmp_path / "test.db")
    yield database
    database.close_all()


@pytest.fixture
def services(tmp_path, monkeypatch):
    monkeypatch.setenv("MUSTACOM_DATA_DIR", str(tmp_path))
    paths = build_paths(tmp_path)
    database = open_database(paths.db)
    svc = Services(database, paths)
    svc.bootstrap()
    yield svc
    database.close_all()


@pytest.fixture
def admin_session(services):
    services.auth.create_user("admin", "Admin!2345", "Administrateur MUSTACOM", "admin")
    session = services.auth.login("admin", "Admin!2345")
    services.current_user = {"id": session.user_id, "username": session.username}
    return session
