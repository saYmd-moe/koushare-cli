from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from platformdirs import user_config_path

from .errors import ApiError


def default_auth_path() -> Path:
    override = os.getenv("KOUSHARE_AUTH_FILE")
    if override:
        return Path(override).expanduser()
    return user_config_path("koushare-cli", appauthor=False) / "auth.json"


@dataclass
class Credentials:
    access_token: str
    refresh_token: str
    access_expires_at: float | None = None
    refresh_expires_at: float | None = None
    username: str | None = None

    @staticmethod
    def _expiry(value: Any, now: float) -> float | None:
        if value in (None, ""):
            return None
        try:
            duration = float(value)
        except (TypeError, ValueError):
            return None
        # The web client adds expire_in directly to Date.now(), so the API
        # durations are milliseconds rather than OAuth-style seconds.
        return now + duration / 1000.0

    @classmethod
    def from_login_data(cls, data: dict[str, Any], *, username: str | None = None) -> "Credentials":
        token_data = data.get("data") if isinstance(data.get("data"), dict) else data
        access = token_data.get("access_token")
        refresh = token_data.get("refresh_token")
        if not access or not refresh:
            raise ApiError("login response did not contain access_token and refresh_token")
        now = time.time()
        return cls(
            access_token=str(access),
            refresh_token=str(refresh),
            access_expires_at=cls._expiry(token_data.get("expire_in"), now),
            refresh_expires_at=cls._expiry(token_data.get("refresh_expire_in"), now),
            username=username,
        )

    def access_expired(self, *, leeway: float = 30.0) -> bool:
        return self.access_expires_at is not None and self.access_expires_at <= time.time() + leeway

    def refresh_expired(self, *, leeway: float = 30.0) -> bool:
        return self.refresh_expires_at is not None and self.refresh_expires_at <= time.time() + leeway


class CredentialStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_auth_path()

    def load(self) -> Credentials | None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, TypeError) as exc:
            raise ApiError(f"could not read auth file {self.path}: {exc}") from exc
        if not isinstance(raw, dict) or raw.get("version") != 1:
            raise ApiError(f"unsupported auth file format: {self.path}")
        try:
            credentials = Credentials(**{key: raw.get(key) for key in asdict(Credentials("", ""))})
        except TypeError as exc:
            raise ApiError(f"invalid auth file: {self.path}") from exc
        if not credentials.access_token or not credentials.refresh_token:
            raise ApiError(f"auth file is missing tokens: {self.path}")
        return credentials

    def save(self, credentials: Credentials) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = {"version": 1, **asdict(credentials)}
        fd, temporary = tempfile.mkstemp(prefix=".auth-", dir=self.path.parent)
        try:
            if os.name != "nt":
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temporary, self.path)
            if os.name != "nt":
                os.chmod(self.path, 0o600)
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise

    def clear(self) -> bool:
        try:
            self.path.unlink()
            return True
        except FileNotFoundError:
            return False
