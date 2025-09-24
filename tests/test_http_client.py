from __future__ import annotations

import gzip
import io
from pathlib import Path

from src.core.http_client import HttpClient
from src.settings import HttpSettings


def _client(tmp_path: Path) -> HttpClient:
    cookie_path = tmp_path / "cookies.txt"
    settings = HttpSettings(timeout=1, min_delay=0, max_delay=0, max_attempts=1, backoff_factor=1)
    return HttpClient(http_settings=settings, cookie_path=cookie_path, default_headers={})


def test_decode_gzip(tmp_path: Path) -> None:
    client = _client(tmp_path)
    payload = b"hello world"
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb") as gz:
        gz.write(payload)
    decoded = client._decode_body(buffer.getvalue(), "gzip")
    assert decoded == payload.decode()
