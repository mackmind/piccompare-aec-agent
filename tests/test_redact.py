"""The shared redaction function: paths and secrets out of any message."""

from __future__ import annotations

from aec.redact import redact


def test_redact_replaces_a_windows_path() -> None:
    assert redact("failed: C:\\Users\\someone\\plan.json") == "failed: <path>"


def test_redact_replaces_a_unc_path() -> None:
    assert redact("failed: \\\\server\\share\\x.json") == "failed: <path>"


def test_redact_replaces_a_posix_path() -> None:
    assert redact("failed: /home/someone/y.json") == "failed: <path>"


def test_redact_replaces_a_quoted_path_whole() -> None:
    # The quotes stay; everything between them goes, spaces included. A pattern
    # that stopped at the first space would leave ``Program Files\x.json``.
    text = redact('cannot open "C:\\Program Files\\Python313\\a b.json": denied')
    assert text == 'cannot open "<path>": denied'


def test_redact_replaces_a_secret_token() -> None:
    text = redact(
        "key sk-test-secret-token and token other-secret",
        secrets=["sk-test-secret-token", "other-secret"],
    )
    assert text == "key <redacted> and token <redacted>"


def test_redact_ignores_an_empty_secret() -> None:
    # An unset environment variable is the normal case, so it must not turn the
    # replacement into a marker between every character.
    assert redact("plain text", secrets=[""]) == "plain text"
    assert redact("plain text", secrets=["", ""]) == "plain text"


def test_redact_leaves_a_url_alone() -> None:
    # A protocol revision or a documentation link must survive the patterns.
    url = "https://modelcontextprotocol.io/specification/2025-06-18"
    assert redact(f"see {url}") == f"see {url}"
