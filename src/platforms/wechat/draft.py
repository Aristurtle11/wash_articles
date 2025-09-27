"""WeChat draft management."""

from __future__ import annotations

import json
from typing import Any, Mapping

import requests

from .api import WeChatApiError
from .credentials import WeChatCredentialStore, WeChatToken


class WeChatDraftClient:
    """Client for creating drafts via the WeChat API."""

    _DRAFT_URL = "https://api.weixin.qq.com/cgi-bin/draft/add"

    def __init__(
        self,
        credential_store: WeChatCredentialStore,
        *,
        timeout: float = 30.0,
    ) -> None:
        self._credentials = credential_store
        self._timeout = timeout

    def create_draft(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Submit a draft payload and return the WeChat response."""
        token = self._credentials.get_token()
        return self._post(payload, token, allow_retry=True)

    def _post(
        self,
        payload: Mapping[str, Any],
        token: WeChatToken,
        *,
        allow_retry: bool,
    ) -> dict[str, Any]:
        url = f"{self._DRAFT_URL}?access_token={token.value}"
        try:
            response = requests.post(url, json=payload, timeout=self._timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise WeChatApiError(
                "草稿提交失败",
                details={"reason": str(exc)},
            ) from exc

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise WeChatApiError(
                "解析微信响应失败",
                details={"response": response.text[:200]},
            ) from exc

        errcode = data.get("errcode")
        if errcode in {40001, 40014, 42001} and allow_retry:
            fresh_token = self._credentials.get_token(force_refresh=True)
            return self._post(payload, fresh_token, allow_retry=False)

        if errcode not in (0, None):
            raise WeChatApiError(
                "草稿提交被微信拒绝",
                details={"errcode": errcode, "errmsg": data.get("errmsg")},
            )

        return data
