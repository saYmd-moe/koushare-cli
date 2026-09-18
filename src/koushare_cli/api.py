from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterable
from typing import Any

import requests

from . import __version__
from .auth import CredentialStore, Credentials
from .errors import ApiError


class KoushareClient:
    API_BASE = "https://api-core.koushare.com"
    # Current front-end request signing salt. This is public client-side material,
    # not a user credential, and may change when Koushare changes its web client.
    SIGNING_SALT = "arfw2r4k4rdwrlmchvcu7q61fs"

    def __init__(
        self,
        *,
        authorization: str | None = None,
        api_base: str | None = None,
        timeout: float = 20.0,
        session: requests.Session | None = None,
        credentials: Credentials | None = None,
        credential_store: CredentialStore | None = None,
    ) -> None:
        self.api_base = (api_base or self.API_BASE).rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.credentials = credentials
        self.credential_store = credential_store
        self.session.headers.update(
            {
                "User-Agent": f"Mozilla/5.0 (compatible; koushare-cli/{__version__})",
                "Referer": "https://www.koushare.com/",
                "Origin": "https://www.koushare.com",
                "Client": "front_web",
                "Accept": "application/json, text/plain, */*",
            }
        )
        if authorization:
            self.session.headers["Authorization"] = authorization
        elif credentials:
            self.session.headers["Authorization"] = credentials.access_token

    @property
    def is_authenticated(self) -> bool:
        return bool(self.session.headers.get("Authorization"))

    @classmethod
    def login(
        cls,
        username: str,
        password: str,
        *,
        area_code: str = "86",
        api_base: str | None = None,
        timeout: float = 20.0,
        session: requests.Session | None = None,
    ) -> Credentials:
        username = username.strip()
        if not username or not password:
            raise ApiError("username and password are required")
        body: dict[str, Any] = {"username": username, "password": password, "flag": False}
        if "@" not in username:
            body["areaCode"] = area_code.lstrip("+")
        client = cls(api_base=api_base, timeout=timeout, session=session)
        payload = client._post("/iam/userLogin/accountLogin", body=body)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ApiError(str(payload.get("msg") or "login failed"))
        return Credentials.from_login_data(data, username=username)

    def _set_credentials(self, credentials: Credentials) -> None:
        self.credentials = credentials
        self.session.headers["Authorization"] = credentials.access_token
        if self.credential_store:
            self.credential_store.save(credentials)

    def refresh_auth(self) -> Credentials:
        if not self.credentials or not self.credentials.refresh_token:
            raise ApiError("not logged in; run `ksdl auth login --username <account>`")
        if self.credentials.refresh_expired():
            raise ApiError("saved login has expired; run `ksdl auth login` again")
        headers = self.signed_headers({}, "GET")
        headers["Authorization"] = self.credentials.refresh_token
        response = self.session.get(
            f"{self.api_base}/iam/userLogin/refreshtoken",
            headers=headers,
            timeout=self.timeout,
        )
        payload = self._payload(response)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ApiError(str(payload.get("msg") or "token refresh failed"))
        refreshed = Credentials.from_login_data(data, username=self.credentials.username)
        self._set_credentials(refreshed)
        return refreshed

    def _ensure_auth(self) -> None:
        if self.credentials and self.credentials.access_expired():
            self.refresh_auth()

    @classmethod
    def make_signature(
        cls,
        params: dict[str, Any] | None,
        method: str,
        *,
        timestamp_ms: int | None = None,
    ) -> tuple[str, int]:
        timestamp = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)
        filtered = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        parts: list[str] = []
        for key in sorted(filtered):
            value = filtered[key]
            if isinstance(value, bool):
                rendered = "true" if value else "false"
            elif isinstance(value, (list, dict)):
                rendered = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
            else:
                rendered = str(value)
            parts.append(f"{key}={rendered}")

        salt_md5 = hashlib.md5(cls.SIGNING_SALT.encode()).hexdigest()
        suffix = f"method={method.upper()}&timestamp={timestamp}&saltmd5={salt_md5}"
        message = "&".join(parts + [suffix]) if parts else suffix
        signature = hashlib.md5(message.encode()).hexdigest()
        return signature, timestamp

    @classmethod
    def signed_headers(cls, params: dict[str, Any] | None, method: str) -> dict[str, str]:
        signature, timestamp = cls.make_signature(params, method)
        return {"ks-sign": signature, "ks-timestamp": str(timestamp)}

    @staticmethod
    def _payload(response: requests.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise ApiError(f"API returned non-JSON data (HTTP {response.status_code})") from exc
        if response.status_code >= 400:
            raise ApiError(f"HTTP {response.status_code}: {data}")
        if isinstance(data, dict):
            success = data.get("success")
            code = str(data.get("code", ""))
            if success is False and not code.startswith("200"):
                raise ApiError(str(data.get("msg") or data.get("message") or data))
            return data
        raise ApiError(f"unexpected API response: {type(data).__name__}")

    def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        _retry_auth: bool = True,
    ) -> dict[str, Any]:
        self._ensure_auth()
        params = params or {}
        response = self.session.get(
            f"{self.api_base}{path}",
            params=params,
            headers=self.signed_headers(params, "GET"),
            timeout=self.timeout,
        )
        payload = self._payload(response)
        if _retry_auth and self.credentials and int(payload.get("code", 0) or 0) in {100005, 100009}:
            self.refresh_auth()
            return self._get(path, params, _retry_auth=False)
        return payload

    def _post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        sign_params: dict[str, Any] | None = None,
        _retry_auth: bool = True,
    ) -> dict[str, Any]:
        self._ensure_auth()
        params = params or {}
        body = body or {}
        signing = sign_params if sign_params is not None else (params or body)
        response = self.session.post(
            f"{self.api_base}{path}",
            params=params,
            json=body,
            headers=self.signed_headers(signing, "POST"),
            timeout=self.timeout,
        )
        payload = self._payload(response)
        if _retry_auth and self.credentials and int(payload.get("code", 0) or 0) in {100005, 100009}:
            self.refresh_auth()
            return self._post(
                path,
                params=params,
                body=body,
                sign_params=sign_params,
                _retry_auth=False,
            )
        return payload

    def live_info(self, live_id: str) -> dict[str, Any]:
        data = self._get(f"/live/v2/live/{live_id}").get("data")
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _extract_list(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            for key in ("list", "records", "rows", "content", "items"):
                items = value.get(key)
                if isinstance(items, list):
                    return [item for item in items if isinstance(item, dict)]
        return []

    def live_playbacks(self, live_id: str, *, page_size: int = 200) -> list[dict[str, Any]]:
        params = {"liveId": int(live_id), "pageNum": 1, "pageSize": page_size}
        payload = self._get("/live/v1/user/livePlayback/list", params)
        items = self._extract_list(payload.get("data"))
        if items:
            return items

        # Koushare exposes freshly ended broadcasts as "fast playback" items,
        # through a separate API from the normal replay catalogue.  The web UI
        # uses this endpoint when isFastPlayback is true and videoNumber is 0.
        payload = self._get("/live/v2/live/fastback/list", {"liveId": int(live_id)})
        fastbacks = self._extract_list(payload.get("data"))
        return [{**item, "isFastBack": True} for item in fastbacks]

    def live_playback(self, live_id: str, video_id: str, *, fastback: bool = False) -> dict[str, Any]:
        if fastback:
            body = {"liveId": int(live_id), "fastBackId": int(video_id)}
            payload = self._post("/live/v2/live/fastback/play", body=body)
            data = payload.get("data")
            if not isinstance(data, dict):
                return {}
            url = data.get("fastbackUrl")
            return {**data, "url": url} if isinstance(url, str) and url else data

        params = {"videoId": video_id}
        payload = self._post(
            f"/live/v2/live/playback/{live_id}",
            params=params,
            body={},
            sign_params=params,
        )
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def video_secret(self, video_id: str) -> str:
        body = {"id": video_id}
        payload = self._post("/video/v1/video/checkVideoAuth", body=body)
        data = payload.get("data")
        secret = data.get("secret") if isinstance(data, dict) else None
        if not secret:
            raise ApiError("video authorization did not return a secret; authentication may be required")
        return str(secret)

    def video_access(self, video_id: str, *, ticket: str = "", password: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"id": video_id, "ticket": ticket}
        if password:
            body["password"] = password
        payload = self._post("/video/v1/video/checkVideoAuthV2", body=body)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ApiError(str(payload.get("msg") or "video authorization failed"))
        code = int(data.get("code", 0) or 0)
        if code != 200000:
            messages = {
                400021: "login required",
                500001: "this video is restricted to followers",
                500002: "this video must be purchased by the logged-in account",
                500003: "this video requires a valid access code",
                500004: "this video is restricted to members",
                2000010: "the account must bind a phone number",
            }
            raise ApiError(messages.get(code, str(data.get("msg") or f"video access denied ({code})")))
        return data

    def video_info_v2(self, video_id: str, *, secret: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"id": video_id}
        if secret:
            params["secret"] = secret
        data = self._get("/video/v1/video/infoV2", params).get("data")
        return data if isinstance(data, dict) else {}

    def video_playback_v2(self, video_id: str, *, ticket: str = "") -> dict[str, Any]:
        params = {"videoId": video_id, "ticket": ticket}
        data = self._get("/video/v1/video/getVideoPlayAddressV2", params).get("data")
        if isinstance(data, list):
            return {"playbackUrls": data}
        if isinstance(data, dict):
            return data
        return {"playbackUrls": []}

    def video_info(self, video_id: str, *, secret: str | None = None) -> dict[str, Any]:
        secret = secret or self.video_secret(video_id)
        params = {"id": video_id, "secret": secret}
        data = self._get("/video/v1/video/info", params).get("data")
        return data if isinstance(data, dict) else {}

    def video_playback(self, video_id: str, *, secret: str | None = None) -> dict[str, Any]:
        secret = secret or self.video_secret(video_id)
        params = {"videoId": video_id, "secret": secret}
        data = self._get("/video/v1/video/getVideoPlayAddress", params).get("data")
        # The endpoint returns a list in current clients. Normalize it to the
        # same shape used by live playback responses.
        if isinstance(data, list):
            return {"playbackUrls": data}
        if isinstance(data, dict):
            return data
        return {"playbackUrls": []}


def iter_quality_items(playback: dict[str, Any]) -> Iterable[dict[str, Any]]:
    groups = playback.get("playbackUrls") or []
    if isinstance(groups, dict):
        groups = [groups]
    if not isinstance(groups, list):
        return
    for group in groups:
        if not isinstance(group, dict):
            continue
        items = group.get("list")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    yield item
        elif any(key in group for key in ("fileUrl", "preUrl", "url", "playUrl")):
            yield group


def media_url(item: dict[str, Any]) -> str | None:
    for key in ("fileUrl", "preUrl", "url", "playUrl"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def available_qualities(playback: dict[str, Any]) -> list[str]:
    qualities: list[str] = []
    for item in iter_quality_items(playback):
        label = item.get("labelEn") or item.get("label")
        if label and str(label) not in qualities:
            qualities.append(str(label))
    return qualities


def choose_media(playback: dict[str, Any], quality: str = "best") -> tuple[str, dict[str, Any]]:
    aliases = {
        "best": "FHD",
        "1080": "FHD",
        "1080p": "FHD",
        "fhd": "FHD",
        "720": "HD",
        "720p": "HD",
        "hd": "HD",
        "480": "SD",
        "480p": "SD",
        "sd": "SD",
    }
    requested = aliases.get(quality.strip().lower(), quality.strip().upper())
    items = list(iter_quality_items(playback))
    if not items:
        direct = playback.get("url") or playback.get("playUrl")
        if isinstance(direct, str) and direct:
            return direct, playback
        raise ApiError("playback response contains no usable media URL")

    def label(item: dict[str, Any]) -> str:
        return str(item.get("labelEn") or item.get("label") or "").upper()

    order = [requested] if requested != "BEST" else []
    for fallback in ("FHD", "HD", "SD"):
        if fallback not in order:
            order.append(fallback)

    for wanted in order:
        for item in items:
            url = media_url(item)
            if url and label(item) == wanted:
                return url, item

    for item in items:
        url = media_url(item)
        if url:
            return url, item
    raise ApiError("playback response contains no usable media URL")
