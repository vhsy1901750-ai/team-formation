# 2026-10-16 22:06 KST
from tf.config import get_secret


def test_get_secret_strips_whitespace(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/postgres\n")
    assert get_secret("DATABASE_URL") == "postgresql://x/postgres"


def test_get_secret_missing_returns_none(monkeypatch):
    monkeypatch.delenv("NOPE_KEY", raising=False)
    assert get_secret("NOPE_KEY") is None
