"""WeChat image upload implementation."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Iterable, Sequence

import requests

from src.platforms.base import ContentBundle, MediaUploadResult, MediaUploader

from .api import WeChatApiError
from .credentials import WeChatCredentialStore, WeChatToken


class WeChatMediaUploader(MediaUploader):
    """Uploads designated images to WeChat永久素材库."""

    _UPLOAD_URL = "https://api.weixin.qq.com/cgi-bin/material/add_material"

    def __init__(
        self,
        credential_store: WeChatCredentialStore,
        *,
        timeout: float = 30.0,
    ) -> None:
        self._credentials = credential_store
        self._timeout = timeout

    def upload_batch(self, bundle: ContentBundle) -> Iterable[MediaUploadResult]:
        """Upload all images within the bundle directory."""
        images = self._sorted_images(bundle.images)
        if not images:
            return []

        token = self._credentials.get_token()
        results: list[MediaUploadResult] = []
        for index, image in enumerate(images, start=1):
            result, token = self._upload_single(image, token, order=index, allow_retry=True)
            results.append(result)
        return results

    def _sorted_images(self, images: Sequence[Path]) -> Sequence[Path]:
        return sorted(
            (img for img in images if img.is_file() and img.name.lower().startswith("image_")),
            key=lambda p: p.name,
        )

    def _upload_single(
        self,
        image: Path,
        token: WeChatToken,
        *,
        order: int,
        allow_retry: bool,
    ) -> tuple[MediaUploadResult, WeChatToken]:
        url = f"{self._UPLOAD_URL}?access_token={token.value}&type=image"
        mime_type = mimetypes.guess_type(image.name)[0] or "image/jpeg"

        with image.open("rb") as stream:
            files = {"media": (image.name, stream, mime_type)}
            try:
                response = requests.post(url, files=files, timeout=self._timeout)
                response.raise_for_status()
            except requests.RequestException as exc:
                raise WeChatApiError(
                    "上传图片失败",
                    details={"path": str(image), "reason": str(exc)},
                ) from exc

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise WeChatApiError(
                "解析微信响应失败",
                details={"path": str(image), "response": response.text[:200]},
            ) from exc

        errcode = data.get("errcode")
        if errcode in self._TOKEN_INVALID_CODES and allow_retry:
            fresh_token = self._credentials.get_token(force_refresh=True)
            return self._upload_single(image, fresh_token, order=order, allow_retry=False)

        if errcode not in (0, None):
            raise WeChatApiError(
                "上传图片被微信拒绝",
                details={
                    "path": str(image),
                    "errcode": errcode,
                    "errmsg": data.get("errmsg"),
                },
            )

        remote_url = data.get("url")
        media_id = data.get("media_id")
        if not remote_url or not media_id:
            raise WeChatApiError(
                "上传成功但缺少 URL 或 media_id",
                details={"path": str(image), "response": data},
            )

        return MediaUploadResult(
            local_path=image, remote_url=remote_url, order=order, media_id=media_id
        ), token

    _TOKEN_INVALID_CODES = {40001, 40014, 42001}
