"""Shared pytest fixtures and hooks for the ČEZ Distribuce integration tests.

Two test groups live in this repo:

* **Offline unit tests** (default) — never touch the network. They mock the HTTP
  layer with ``requests_mock`` and assert on parsing / retry / URL logic.

* **Integration tests** (marked ``@pytest.mark.integration``) — exercise the
  real ČEZ Distribuce portal. They require the ``CEZ_USERNAME`` and
  ``CEZ_PASSWORD`` environment variables and are skipped automatically when
  those are not set, so the suite stays green in CI without secrets.

Credentials lookup order for integration tests:

1. Environment variables ``CEZ_USERNAME`` / ``CEZ_PASSWORD``.
2. A git-ignored ``.env.local`` file in the repo root (key=value lines), as a
   convenience for local development without exporting env vars.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

# Environment variable names that supply live portal credentials.
ENV_USERNAME = "CEZ_USERNAME"
ENV_PASSWORD = "CEZ_PASSWORD"

# Path to the optional, git-ignored env file used as a credentials fallback.
ENV_LOCAL_PATH = Path(__file__).resolve().parent.parent / ".env.local"


def _read_env_file(path: Path) -> dict[str, str]:
    """Parse a .env-style file into a dict of the CEZ_* keys we care about.

    Pure function: reads the file, returns only ``CEZ_USERNAME`` / ``CEZ_PASSWORD``
    entries (ignoring other keys). Comments (``#``), blank lines and surrounding
    whitespace are ignored; surrounding single/double quotes around the value are
    stripped. Returns ``{}`` if the file does not exist or cannot be read.
    """
    wanted = {ENV_USERNAME, ENV_PASSWORD}
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return result
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key in wanted and value:
            result[key] = value
    return result


def _load_env_local_if_present() -> None:
    """Load unset CEZ_* vars from ``.env.local`` (key=value lines).

    Existing environment variables always take precedence, so CI can override.
    Only the two expected keys are applied.
    """
    for key, value in _read_env_file(ENV_LOCAL_PATH).items():
        if not os.environ.get(key):
            os.environ[key] = value


# Load .env.local at import time so collection-time skip logic sees the vars.
_load_env_local_if_present()


def _has_credentials() -> bool:
    """Return True iff both CEZ_USERNAME and CEZ_PASSWORD are available.

    Sources (in order): real environment variables, then ``.env.local`` (loaded
    into os.environ at import time by :func:`_load_env_local_if_present`).
    """
    return bool(os.environ.get(ENV_USERNAME)) and bool(os.environ.get(ENV_PASSWORD))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]):
    """Auto-skip integration tests when no live credentials are available.

    This keeps ``pytest -q`` green out of the box (e.g. in CI) while still
    allowing ``CEZ_USERNAME=... CEZ_PASSWORD=... pytest -m integration`` to run
    the live tests locally.
    """
    if _has_credentials():
        return
    skip_marker = pytest.mark.skip(
        reason=(
            f"integration test: set {ENV_USERNAME} and {ENV_PASSWORD} "
            "environment variables to run"
        )
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_marker)


@pytest.fixture(scope="module")
def env_credentials():
    """Yield (username, password) for the live portal (module-scoped).

    Sources (in order): ``CEZ_USERNAME`` / ``CEZ_PASSWORD`` env vars, then the
    git-ignored ``.env.local`` in the repo root (loaded at import time). Use
    only from integration tests — they are auto-skipped when neither source
    provides both values, so by the time this fixture runs they are present.
    """
    return os.environ[ENV_USERNAME], os.environ[ENV_PASSWORD]


# ---------------------------------------------------------------------------
# Network access for live integration tests
# ---------------------------------------------------------------------------
# pytest-homeassistant-custom-component patches socket.getaddrinfo /
# gethostbyname / gethostbyname_ex with host-validating stubs so that no test
# can resolve external DNS. That is desirable for the offline HA tests, but it
# breaks the live integration tests that must talk to mepas.cez.cz /
# dip.cezdistribuce.cz. For tests marked `integration` we restore the real
# resolvers for the duration of the test.
@pytest.fixture(autouse=True)
def _enable_network_for_integration(request):
    """Restore real socket DNS resolution + sockets for @pytest.mark.integration.

    Function-scoped on purpose: pytest-homeassistant-custom-component re-applies
    its socket/DNS patches before every test, so we must lift them before every
    test too. Without this, all external DNS and socket.connect are blocked,
    which is desirable for the offline HA tests but breaks live integration
    tests.
    """
    if "integration" not in request.keywords:
        yield
        return

    import socket

    saved_getaddrinfo = socket.getaddrinfo
    saved_gethostbyname = socket.gethostbyname
    saved_gethostbyname_ex = socket.gethostbyname_ex
    saved_socket_cls = socket.socket
    saved_socket_connect = socket.socket.connect

    # pytest_homeassistant_custom_component captured the real getaddrinfo at
    # import time before patching; reuse it if available.
    try:
        from pytest_homeassistant_custom_component import plugins as ha_plugins

        real_getaddrinfo = ha_plugins._real_getaddrinfo
    except (ImportError, AttributeError):
        real_getaddrinfo = None

    try:
        import pytest_socket

        # socket_allow_hosts(None) is a no-op (returns early), so we must reach
        # for pytest-socket internals to truly lift the connect() guard.
        # _remove_restrictions() restores socket.socket / socket.socket.connect
        # / getaddrinfo to their real implementations.
        if hasattr(pytest_socket, "_remove_restrictions"):
            pytest_socket._remove_restrictions()
        else:  # pragma: no cover - fallback for older pytest-socket
            socket.socket.connect = pytest_socket._true_connect  # type: ignore[attr-defined]
        if real_getaddrinfo is not None:
            socket.getaddrinfo = real_getaddrinfo
    except ImportError:
        pass

    yield

    # Restore the HA-plugin patched versions so subsequent offline tests stay
    # network-safe.
    socket.getaddrinfo = saved_getaddrinfo
    socket.gethostbyname = saved_gethostbyname
    socket.gethostbyname_ex = saved_gethostbyname_ex
    socket.socket = saved_socket_cls  # type: ignore[misc]
    socket.socket.connect = saved_socket_connect
