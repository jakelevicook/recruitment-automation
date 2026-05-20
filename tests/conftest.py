import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    tmp = tempfile.TemporaryDirectory()
    db_path = Path(tmp.name) / "shipments.db"
    from app import db as db_module
    monkeypatch.setattr(db_module, "_DB_PATH", db_path)
    yield
    tmp.cleanup()
