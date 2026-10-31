"""One redaction function for every surface that shows an error message.

A handler error quotes whatever the failing library put in it, and that can be
an absolute path or a value from the environment. A caller needs to know what
failed, not where this machine keeps its files.

Moved out of :mod:`aec.mcp_server` in W1-1 so the command line and the local web
page do not grow a second copy of the patterns. The 2000-character limit the
server also applies stays in the server: a length limit belongs to that
transport, not to redaction.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

# A path may contain spaces (a Windows "Program Files" directory, for one), so a
# path token ends at a quote or a newline, not at the first whitespace: stopping
# at a space would redact the head and send the rest of the path to the caller.
_WINDOWS_PATH = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/][^\"'\r\n]*")
_UNC_PATH = re.compile(r"\\\\[^\"'\r\n]*")
_POSIX_PATH = re.compile(r"(?<![A-Za-z0-9_:./])/(?:[^\"'/\r\n]+/)*[^\"'\r\n]*")
_PATH_PATTERNS = (_WINDOWS_PATH, _UNC_PATH, _POSIX_PATH)


def redact(text: str, *, secrets: Sequence[str] = ()) -> str:
    """Return ``text`` with every absolute path and every given secret removed.

    ``secrets`` holds the values to hide, not their names: the caller owns the
    decision about which environment variables matter. An empty value is
    ignored, so an unset variable costs nothing.
    """
    cleaned = text
    for pattern in _PATH_PATTERNS:
        cleaned = pattern.sub("<path>", cleaned)
    for secret in secrets:
        if secret:
            cleaned = cleaned.replace(secret, "<redacted>")
    return cleaned
