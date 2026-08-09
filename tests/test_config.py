import re
import subprocess
from pathlib import Path

import pytest

from main import create_app


def test_application_uses_environment_secret(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "environment-test-secret")
    app = create_app({"TESTING": True})
    assert app.config["SECRET_KEY"] == "environment-test-secret"


def test_missing_secret_fails_safely(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY is required"):
        create_app({"TESTING": True})


def test_source_has_no_hardcoded_secret():
    source = Path("main.py").read_text(encoding="utf-8")
    assert not re.search(r'SECRET_KEY.{0,20}=[^\n]*["\'][0-9a-f]{32,}["\']', source)


def test_env_files_are_ignored():
    result = subprocess.run(
        ["git", "check-ignore", ".env", ".env.local"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert set(result.stdout.splitlines()) == {".env", ".env.local"}
