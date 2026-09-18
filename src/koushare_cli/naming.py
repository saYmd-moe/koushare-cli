from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .errors import KoushareError

DEFAULT_TEMPLATE = "{title} [{video_id}].{ext}"


def _first_text(*sources: dict[str, Any], keys: tuple[str, ...]) -> str:
    for source in sources:
        for key in keys:
            value = source.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return ""


def build_name_context(
    *,
    title: str,
    video_id: str,
    live_id: str | None = None,
    room_id: str | None = None,
    quality: str = "",
    height: int | str | None = None,
    index: int = 1,
    item: dict[str, Any] | None = None,
    live_info: dict[str, Any] | None = None,
    ext: str = "mp4",
) -> dict[str, Any]:
    item = item or {}
    live_info = live_info or {}
    date = _first_text(
        item,
        live_info,
        keys=(
            "date",
            "startTime",
            "start_time",
            "beginTime",
            "createTime",
            "publishTime",
            "liveDate",
            "livedate",
        ),
    )
    speaker = _first_text(
        item,
        live_info,
        keys=("speaker", "speakerName", "lecturer", "lecturerName", "author", "nickname", "userName"),
    )
    live_title = _first_text(live_info, keys=("title", "name", "liveTitle", "ltitle"))
    return {
        "title": title,
        "video_id": str(video_id),
        "id": str(video_id),
        "live_id": str(live_id or ""),
        "room_id": str(room_id or ""),
        "live_title": live_title,
        "quality": quality,
        "height": height or "",
        "index": index,
        "date": date,
        "speaker": speaker,
        "ext": ext.lstrip("."),
    }


def sanitize_filename(value: str, *, fallback: str = "koushare-video", max_length: int = 240) -> str:
    # Keep naming deterministic across Linux/macOS/Windows and prevent a template
    # from accidentally turning into a path.
    value = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", value).strip().strip(".")
    value = re.sub(r"\s+", " ", value)
    if not value:
        value = fallback

    suffix = Path(value).suffix
    if suffix and len(suffix) <= 12:
        stem_limit = max(1, max_length - len(suffix))
        stem = Path(value).stem[:stem_limit].rstrip()
        return f"{stem}{suffix}"
    return value[:max_length].rstrip()


def render_filename(
    template: str,
    context: dict[str, Any],
    *,
    fallback: str,
    ensure_extension: str = ".mp4",
) -> str:
    try:
        rendered = template.format_map(context)
    except KeyError as exc:
        keys = ", ".join(sorted(context))
        raise KoushareError(f"unknown filename template field {exc.args[0]!r}; available fields: {keys}") from exc
    except (ValueError, IndexError) as exc:
        raise KoushareError(f"invalid filename template: {exc}") from exc

    rendered = sanitize_filename(rendered, fallback=fallback)
    if not Path(rendered).suffix:
        rendered += ensure_extension
    return rendered


def literal_filename(name: str, *, fallback: str, ensure_extension: str = ".mp4") -> str:
    rendered = sanitize_filename(name, fallback=fallback)
    if not Path(rendered).suffix:
        rendered += ensure_extension
    return rendered
