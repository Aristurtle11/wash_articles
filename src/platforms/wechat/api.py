"""WeChat API helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from typing import Any, Mapping
import urllib.error
import urllib.parse
import urllib.request


class WeChatApiError(RuntimeError):
    """Raised when WeChat API calls fail."""

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = dict(details or {})

    def __str__(self) -> str:
        base = super().__str__()
        if not self.details:
            return base
        try:
            detail_repr = json.dumps(self.details, ensure_ascii=False)
        except TypeError:
            detail_repr = str(self.details)
        return f"{base} | 详情: {detail_repr}"


@dataclass(slots=True)
class AccessTokenResponse:
    """Parsed access token response."""

    token: str
    expires_at: datetime


class WeChatApiClient:
    """Minimal client for interacting with WeChat Open Platform APIs."""

    _TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"

    def __init__(self, *, timeout: float = 10.0) -> None:
        self._timeout = timeout

    def fetch_access_token(self, app_id: str, app_secret: str) -> AccessTokenResponse:
        """Retrieve a fresh access token from WeChat."""
        params = {
            "grant_type": "client_credential",
            "appid": app_id,
            "secret": app_secret,
        }
        url = f"{self._TOKEN_URL}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url=url, method="GET")

        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:  # pragma: no cover - network failure path
            raise WeChatApiError(
                "调用微信服务器失败",
                details={"status": exc.code, "reason": exc.reason},
            ) from exc
        except urllib.error.URLError as exc:  # pragma: no cover - network failure path
            raise WeChatApiError(
                "无法连接至微信服务器",
                details={"reason": str(exc.reason)},
            ) from exc

        try:
            data: dict[str, Any] = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WeChatApiError("解析微信响应失败", details={"body": raw[:200]}) from exc

        if "errcode" in data and data.get("errcode") != 0:
            raise WeChatApiError(
                "获取 access_token 失败",
                details={"errcode": data.get("errcode"), "errmsg": data.get("errmsg")},
            )

        token = data.get("access_token")
        expires_in = data.get("expires_in")
        if not token or not expires_in:
            raise WeChatApiError("响应缺少 access_token 或 expires_in 字段", details=data)

        try:
            expires_seconds = int(expires_in)
        except (TypeError, ValueError) as exc:
            raise WeChatApiError("expires_in 字段格式不正确", details={"expires_in": expires_in}) from exc

        expires_at = datetime.now(tz=UTC) + timedelta(seconds=expires_seconds)
        return AccessTokenResponse(token=token, expires_at=expires_at)
