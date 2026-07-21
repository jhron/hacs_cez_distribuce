"""Unit tests for the conftest helpers (credentials loading from .env.local).

These test the pure parsing logic without touching os.environ or the real
``.env.local`` file, so they run fully offline and do not depend on whether
credentials happen to be present.
"""
from __future__ import annotations

from pathlib import Path

from tests.conftest import ENV_PASSWORD, ENV_USERNAME, _read_env_file


def test_read_env_file_returns_empty_when_missing(tmp_path: Path):
    assert _read_env_file(tmp_path / "does_not_exist.env") == {}


def test_read_env_file_parses_username_and_password(tmp_path: Path):
    f = tmp_path / ".env.local"
    f.write_text("CEZ_USERNAME=user@example.com\nCEZ_PASSWORD=secret123\n", encoding="utf-8")
    assert _read_env_file(f) == {
        ENV_USERNAME: "user@example.com",
        ENV_PASSWORD: "secret123",
    }


def test_read_env_file_ignores_comments_and_blanks(tmp_path: Path):
    f = tmp_path / ".env.local"
    f.write_text(
        "# This is a comment\n"
        "\n"
        "   # indented comment\n"
        "CEZ_USERNAME=user@example.com\n"
        "\n"
        "CEZ_PASSWORD=p\n",
        encoding="utf-8",
    )
    assert _read_env_file(f) == {ENV_USERNAME: "user@example.com", ENV_PASSWORD: "p"}


def test_read_env_file_strips_surrounding_quotes(tmp_path: Path):
    f = tmp_path / ".env.local"
    f.write_text(
        'CEZ_USERNAME="double@quoted.com"\n'
        "CEZ_PASSWORD='single'\n",
        encoding="utf-8",
    )
    assert _read_env_file(f) == {
        ENV_USERNAME: "double@quoted.com",
        ENV_PASSWORD: "single",
    }


def test_read_env_file_ignores_unrelated_keys(tmp_path: Path):
    """Only CEZ_USERNAME / CEZ_PASSWORD are surfaced; other keys are skipped."""
    f = tmp_path / ".env.local"
    f.write_text(
        "DEBUG=True\n"
        "HOME_ASSISTANT_TOKEN=abc\n"
        "CEZ_USERNAME=user@example.com\n",
        encoding="utf-8",
    )
    assert _read_env_file(f) == {ENV_USERNAME: "user@example.com"}


def test_read_env_file_skips_empty_values(tmp_path: Path):
    """An empty value should not be treated as a credential."""
    f = tmp_path / ".env.local"
    f.write_text("CEZ_USERNAME=\nCEZ_PASSWORD=\n", encoding="utf-8")
    assert _read_env_file(f) == {}


def test_read_env_file_handles_windows_line_endings(tmp_path: Path):
    f = tmp_path / ".env.local"
    f.write_bytes(
        b"CEZ_USERNAME=user@example.com\r\n"
        b"CEZ_PASSWORD=p\r\n"
    )
    assert _read_env_file(f) == {
        ENV_USERNAME: "user@example.com",
        ENV_PASSWORD: "p",
    }


def test_read_env_file_preserves_values_with_equals_sign(tmp_path: Path):
    """Values that themselves contain '=' must survive the partition()."""
    f = tmp_path / ".env.local"
    f.write_text("CEZ_PASSWORD=base64==\n", encoding="utf-8")
    assert _read_env_file(f) == {ENV_PASSWORD: "base64=="}
