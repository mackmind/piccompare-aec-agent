#!/usr/bin/env python3
"""Check that the submission repository is publicly readable."""

from __future__ import annotations

import urllib.error
import urllib.request

URL = "https://github.com/mackmind/piccompare-aec-agent"


def main() -> int:
    try:
        with urllib.request.urlopen(URL, timeout=20) as response:
            code = response.status
    except urllib.error.HTTPError as error:
        code = error.code
    except OSError as error:
        print(f"{URL} -> ERROR {error}")
        return 1
    print(f"{URL} -> {code}")
    return 0 if code == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
