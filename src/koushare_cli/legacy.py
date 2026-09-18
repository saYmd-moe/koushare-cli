from __future__ import annotations

from typing import Any

import requests

from .errors import ApiError


class LegacyClient:
    """Compatibility client for old /lives/room/<roomId> links.

    This intentionally supports only normal public/password-protected access.
    A password must be supplied by the user; the client does not try to bypass it.
    """

    API_BASE = "https://api.koushare.com/api/api-live"

    def __init__(self, *, token: str | None = None, timeout: float = 20.0) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://www.koushare.com/",
                "User-Agent": "Mozilla/5.0 (compatible; koushare-cli/0.1)",
            }
        )
        if token:
            self.session.headers["Cookie"] = f"Token={token}"

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self.session.get(f"{self.API_BASE}{path}", params=params, timeout=self.timeout)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ApiError(f"legacy API returned non-JSON data (HTTP {response.status_code})") from exc
        if response.status_code >= 400:
            raise ApiError(f"legacy API HTTP {response.status_code}: {payload}")
        return payload if isinstance(payload, dict) else {}

    def room_info(self, room_id: str, *, password: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"roomid": room_id, "allData": 1}
        if password:
            params["password"] = password
        payload = self._get("/getLiveByRoomid", params)
        code = str(payload.get("code", ""))
        if code and code != "200":
            msg = payload.get("msg") or payload.get("message") or payload
            raise ApiError(f"legacy room API returned {code}: {msg}")
        data = payload.get("data")
        return data if isinstance(data, dict) else {}
