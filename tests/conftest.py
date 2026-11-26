import os

import pytest

from app import create_app
from app.models import db
from app.seed import seed_basisdaten, seed_demo


@pytest.fixture
def app(tmp_path):
    # Standard: frische SQLite-Datei pro Test. Mit TEST_DATABASE_URL=postgresql+psycopg://… laufen die Tests
    # gegen PostgreSQL (die Datenbank wird pro Test geleert).
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path}/t.sqlite"
    app = create_app({"SQLALCHEMY_DATABASE_URI": url,
                      "UPLOAD_DIR": str(tmp_path / "dateien"), "TESTING": True, "TESTING_NO_CSRF": True})
    with app.app_context():
        if url.startswith("postgresql"):
            db.drop_all()
            db.create_all()
        seed_basisdaten()
        seed_demo()
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def lp(app):
    """Als Demo-Lehrperson angemeldeter Testclient."""
    c = app.test_client()
    c.post("/login", data={"benutzername": "lp", "passwort": "lp-demo-2026"}, follow_redirects=True)
    return c
