from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from .errors import UnsupportedUrl


@dataclass(frozen=True)
class Target:
    kind: str
    live_id: str | None = None
    video_id: str | None = None
    room_id: str | None = None


def parse_target(value: str) -> Target:
    raw = value.strip()
    if not raw:
        raise UnsupportedUrl("empty target")

    prefixed = re.fullmatch(r"(?i)(live|video|room):([0-9]+)", raw)
    if prefixed:
        kind, ident = prefixed.groups()
        kind = kind.lower()
        if kind == "live":
            return Target("live", live_id=ident)
        if kind == "video":
            return Target("video", video_id=ident)
        return Target("legacy-room", room_id=ident)

    # A bare numeric id is most useful for current live pages. Use video:<id>
    # when an unambiguous standalone video id is intended.
    if raw.isdigit():
        return Target("live", live_id=raw)

    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host not in {"koushare.com", "www.koushare.com"}:
        raise UnsupportedUrl(f"not a supported Koushare URL: {value}")

    live = re.search(r"/live/details/([0-9]+)", parsed.path)
    if live:
        query = parse_qs(parsed.query)
        video_id = (query.get("vid") or query.get("videoId") or [None])[0]
        return Target("live", live_id=live.group(1), video_id=str(video_id) if video_id else None)

    video = re.search(r"/video/(?:details|videodetail)/([0-9]+)", parsed.path, re.I)
    if video:
        return Target("video", video_id=video.group(1))

    room = re.search(r"/lives?/room/([0-9]+)", parsed.path, re.I)
    if room:
        return Target("legacy-room", room_id=room.group(1))

    raise UnsupportedUrl(f"unrecognized Koushare URL: {value}")
