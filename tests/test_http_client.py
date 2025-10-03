from __future__ import annotations

import gzip
import io
import json
from pathlib import Path

from src.core.http_client import HttpClient
from src.settings import HttpSettings, PathSettings


def _http_settings() -> HttpSettings:
    return HttpSettings(
        timeout=1,
        min_delay=0,
        max_delay=0,
        max_attempts=1,
        backoff_factor=1,
        transport="auto",
    )


def _make_paths(root: Path) -> PathSettings:
    root.mkdir(parents=True, exist_ok=True)
    state_dir = root / "state"
    return PathSettings(
        data_dir=root / "data",
        raw_dir=root / "raw",
        translated_dir=root / "translated",
        formatted_dir=root / "formatted",
        titles_dir=root / "titles",
        artifacts_dir=root / "artifacts",
        log_dir=root / "logs",
        state_dir=state_dir,
        cookie_jar=state_dir / "cookies.txt",
        header_jar=state_dir / "headers.json",
        default_channel=None,
    )


def _client(root: Path) -> HttpClient:
    return HttpClient(http_settings=_http_settings(), paths=_make_paths(root))


def test_decode_gzip(tmp_path: Path) -> None:
    client = _client(tmp_path / "gzip")
    payload = b"hello world"
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb") as gz:
        gz.write(payload)
    decoded = client._decode_body(buffer.getvalue(), "gzip")
    assert decoded == payload.decode()


def test_header_jar_preferred_when_present(tmp_path: Path) -> None:
    root = tmp_path / "headers"
    paths = _make_paths(root)
    paths.header_jar.parent.mkdir(parents=True, exist_ok=True)
    expected = {
        "user-agent": "custom-agent/1.0",
        "accept": "text/html",
        ":authority": "example.org",
        "host": "example.org",
        "accept-encoding": "gzip, deflate, br, zstd",
    }
    paths.header_jar.write_text(json.dumps(expected), encoding="utf-8")

    client = HttpClient(http_settings=_http_settings(), paths=paths)

    headers = client.default_headers
    assert headers.get("user-agent") == "custom-agent/1.0"
    assert headers.get("accept") == "text/html"
    assert ":authority" not in headers
    assert "host" not in headers
    assert headers.get("accept-encoding") == "gzip, deflate, br"
    # Fallback headers should still be populated when missing from capture.
    assert "accept-language" in headers


def test_header_jar_created_when_missing(tmp_path: Path) -> None:
    root = tmp_path / "missing"
    paths = _make_paths(root)

    client = HttpClient(http_settings=_http_settings(), paths=paths)

    headers_path = paths.header_jar
    assert headers_path.exists()
    loaded = json.loads(headers_path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    assert client.default_headers == loaded


def test_invalid_header_jar_falls_back(tmp_path: Path) -> None:
    root = tmp_path / "invalid"
    paths = _make_paths(root)
    paths.header_jar.parent.mkdir(parents=True, exist_ok=True)
    paths.header_jar.write_text("{invalid", encoding="utf-8")

    client = HttpClient(http_settings=_http_settings(), paths=paths)

    loaded = json.loads(paths.header_jar.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    assert client.default_headers == loaded
    assert "user-agent" in {k.lower(): v for k, v in loaded.items()}
