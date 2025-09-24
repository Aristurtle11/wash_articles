"""Backwards-compatible shim for the standalone cookie fetcher."""

from __future__ import annotations

from scripts.fetch_cookies import main


if __name__ == "__main__":
    main()
