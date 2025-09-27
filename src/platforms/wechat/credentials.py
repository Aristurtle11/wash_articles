"""Credential management for WeChat integrations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from os import environ
from pathlib import Path
from typing import Mapping, Optional


@dataclass(slots=True)
class WeChatToken:
    """Holds the current access token state."""

    value: str
    expires_at: datetime


class WeChatCredentialStore:
    """Resolves AppID/AppSecret from environment variables and manages token caching."""

    def __init__(
        self,
        *,
        token_cache_path: Path,
        env: Mapping[str, str] | None = None,
        env_app_id_key: str = "WECHAT_APP_ID",
        env_app_secret_key: str = "WECHAT_APP_SECRET",
    ) -> None:
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
        """Retrieve the cached token when available."""
        # Skeleton implementation keeps persistence logic stubbed out.
        return None

    def store_token(self, token: WeChatToken) -> None:
        """Persist the token details for reuse."""
        _ = token
        # TODO: Implement safe write with file permissions.
