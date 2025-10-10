import types

from custom_components.cez_distribuce.rest_client.rest_client import is_array, log_history


def test_is_array():
    # Non-strings sequences are arrays
    assert is_array([1, 2, 3]) is True
    assert is_array((1, 2)) is True
    # Strings are sequences but must return False
    assert is_array("abc") is False
    # Non-sequences are False
    assert is_array(123) is False
    assert is_array({"a": 1}) is False


def test_log_history_formats_each_hop_on_new_line():
    # Build a minimal fake Response-like object with .history list containing
    # objects that have the required attributes.
    hop1 = types.SimpleNamespace(status_code=302, is_redirect=True, headers={"Location": "http://b"}, url="http://a")
    hop2 = types.SimpleNamespace(status_code=200, is_redirect=False, headers={"Content-Type": "text/html"}, url="http://b")

    response_like = types.SimpleNamespace(history=[hop1, hop2])

    out = log_history(response_like)  # type: ignore[arg-type]

    # Expect two lines, each containing the status code and URL
    lines = [ln for ln in out.split("\n") if ln]
    assert len(lines) == 2
    assert "302" in lines[0] and "http://a" in lines[0]
    assert "200" in lines[1] and "http://b" in lines[1]
