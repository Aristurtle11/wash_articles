"""Credential management for WeChat integrations."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from os import environ
from pathlib import Path
from typing import Mapping, Optional

from .api import AccessTokenResponse, WeChatApiClient


@dataclass(slots=True)
class WeChatToken:
    """Holds the current access token state."""

    value: str
    expires_at: datetime


class WeChatCredentialStore:
    """Resolves AppID/AppSecret from environment variables and manages token caching."""

    _REFRESH_MARGIN = timedelta(minutes=5)

    def __init__(
        self,
        *,
        token_cache_path: Path,
        api_client: WeChatApiClient,
        env: Mapping[str, str] | None = None,
        env_app_id_key: str = "WECHAT_APP_ID",
        env_app_secret_key: str = "WECHAT_APP_SECRET",
    ) -> None:
        self._api_client = api_client
        self._env = env if env is not None else environ
        self._token_cache_path = token_cache_path
        self._env_app_id_key = env_app_id_key
        self._env_app_secret_key = env_app_secret_key

    def load_app_id(self) -> str:
        """Fetch the configured AppID from environment variables."""
        try:
            return self._env[self._env_app_id_key]
        except KeyError as exc:
            raise RuntimeError(
                f"缺少环境变量 {self._env_app_id_key}，无法初始化微信公众号凭证"
            ) from exc

    def load_app_secret(self) -> str:
        """Fetch the configured AppSecret from environment variables."""
        try:
            return self._env[self._env_app_secret_key]
        except KeyError as exc:
            raise RuntimeError(
                f"缺少环境变量 {self._env_app_secret_key}，无法初始化微信公众号凭证"
            ) from exc

    def load_cached_token(self) -> Optional[WeChatToken]:
        """Retrieve the cached token when available and not expired."""
        path = self._token_cache_path
        if not path.exists():
            return None
        try:
            raw = path.read_text(encoding="utf-8")
            payload = json.loads(raw)
            token_value = payload["access_token"]
            expires_at = datetime.fromisoformat(payload["expires_at"])
            token = WeChatToken(value=token_value, expires_at=expires_at)
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            return None
        if self._is_expired(token):
            return None
        return token

    def store_token(self, token: WeChatToken) -> None:
        """Persist the token details for reuse."""
        payload = {
            "access_token": token.value,
            "expires_at": token.expires_at.isoformat(),
        }
        path = self._token_cache_path
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(payload)
        with tempfile.NamedTemporaryFile("w", delete=False, dir=str(path.parent)) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        tmp_path.replace(path)
        if os.name != "nt":  # set stricter permissions on POSIX systems
            os.chmod(path, 0o600)

    def request_new_token(self) -> WeChatToken:
        """Fetch a fresh token from WeChat and return it."""
        app_id = self.load_app_id()
        app_secret = self.load_app_secret()
        response: AccessTokenResponse = self._api_client.fetch_access_token(app_id, app_secret)
        token = WeChatToken(value=response.token, expires_at=response.expires_at)
        self.store_token(token)
        return token

    def get_token(self, *, force_refresh: bool = False) -> WeChatToken:
        """Return a valid access token, refreshing if needed."""
        if not force_refresh:
            cached = self.load_cached_token()
            if cached:
                return cached
        return self.request_new_token()

    def _is_expired(self, token: WeChatToken) -> bool:
        now = datetime.now(tz=UTC)
        return token.expires_at <= now + self._REFRESH_MARGIN
