"""
Shared pytest fixtures for post-op-triage tests.
Uses a fresh in-memory SQLite database for each test.
"""

import os
import tempfile
import pytest
from src import db


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    """Give every test a clean SQLite database."""
    db_path = tmp_path / "test_triage.db"
    # Monkey-patch the module-level path so all db functions use it
    db._DB_PATH = db_path
    # Reset thread-local connection so next call creates a new one
    if hasattr(db._local, "conn"):
        try:
            db._local.conn.close()
        except Exception:
            pass
        db._local.conn = None
    db.init_db()
    yield db_path
    if hasattr(db._local, "conn") and db._local.conn:
        try:
            db._local.conn.close()
        except Exception:
            pass
        db._local.conn = None


@pytest.fixture
def session_id():
    """Create a standard test session and return its ID."""
    return db.create_session("Total Knee Replacement", 7, "TestPatient")


@pytest.fixture
def session_with_data(session_id):
    """Session pre-loaded with symptoms, vitals, and meds."""
    db.log_symptom(session_id, "pain", 3, "mild ache")
    db.log_symptom(session_id, "pain", 5, "getting worse")
    db.log_symptom(session_id, "swelling", 4, "right knee swollen")
    db.log_vital(session_id, "temperature", 100.2, "F")
    db.log_vital(session_id, "heart_rate", 88, "bpm")
    db.log_med_taken(session_id, "ibuprofen", "400mg", "4 hours ago")
    db.log_med_taken(session_id, "acetaminophen", "500mg", "2 hours ago")
    return session_id
