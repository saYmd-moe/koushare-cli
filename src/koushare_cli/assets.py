from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests

from .downloader import HTTP_HEADERS
from .errors import DownloadError


_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}
_SUBTITLE_EXTENSIONS = {".srt", ".vtt", ".ass", ".ssa", ".lrc", ".json"}


def _first_text(sources: list[dict[str, Any]], keys: tuple[str, ...]) -> str:
    for source in sources:
        for key in keys:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def cover_url(metadata: dict[str, Any], live_metadata: dict[str, Any]) -> str:
    return _first_text(
        [metadata, live_metadata],
        ("coverUrl", "cover", "coverURL", "thumbnailUrl", "thumbnail", "poster"),
    )


def description_html(metadata: dict[str, Any], live_metadata: dict[str, Any]) -> str:
    sections: list[tuple[str, str]] = []
    seen: set[str] = set()
    for source in (metadata, live_metadata):
        for key, label in (
            ("blurb", "简介"),
            ("brief", "简介"),
            ("description", "简介"),
            ("introduction", "简介"),
            ("blurbEn", "Description"),
            ("briefEn", "Description"),
            ("descriptionEn", "Description"),
        ):
            value = source.get(key)
            if isinstance(value, str) and value.strip() and value.strip() not in seen:
                seen.add(value.strip())
                sections.append((label, value.strip()))
    if not sections:
        return ""
    body = "\n".join(
        f"<section><h2>{html.escape(label)}</h2>\n{value}\n</section>"
        for label, value in sections
    )
    return f"<!doctype html>\n<meta charset=\"utf-8\">\n{body}\n"


def subtitle_urls(metadata: dict[str, Any], live_metadata: dict[str, Any]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    seen: set[str] = set()

    def visit(value: Any, path: tuple[str, ...] = ()) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, (*path, str(key)))
            return
        if isinstance(value, list):
            for index, child in enumerate(value, start=1):
                visit(child, (*path, str(index)))
            return
        if not isinstance(value, str) or not value.startswith(("https://", "http://")):
            return
        lowered = ".".join(path).lower()
        if not any(token in lowered for token in ("subtitle", "caption", "transcript")):
            return
        if value in seen:
            return
        seen.add(value)
        hint = next(
            (part for part in reversed(path[:-1]) if re.fullmatch(r"[A-Za-z]{2,8}(?:-[A-Za-z]{2,8})?", part)),
            f"subtitle-{len(found) + 1}",
        )
        found.append((hint, value))
    visit(metadata)
    visit(live_metadata)
    return found


def _extension(url: str, allowed: set[str], fallback: str) -> str:
    suffix = Path(urlsplit(url).path).suffix.lower()
    return suffix if suffix in allowed else fallback


def download_asset(url: str, output: Path, *, timeout: float = 30.0) -> Path:
    if not url.startswith(("https://", "http://")):
        raise DownloadError("asset URL must use HTTP or HTTPS")
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_suffix(output.suffix + ".part")
    try:
        with requests.get(url, headers=HTTP_HEADERS, timeout=timeout, stream=True) as response:
            response.raise_for_status()
            with partial.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 128):
                    if chunk:
                        handle.write(chunk)
        partial.replace(output)
    except (OSError, requests.RequestException) as exc:
        partial.unlink(missing_ok=True)
        raise DownloadError(f"failed to download sidecar asset: {exc}") from exc
    return output


def cover_path(video_path: Path, url: str) -> Path:
    return video_path.with_suffix(".cover" + _extension(url, _IMAGE_EXTENSIONS, ".jpg"))


def subtitle_path(video_path: Path, hint: str, url: str, index: int) -> Path:
    safe_hint = re.sub(r"[^A-Za-z0-9_-]+", "-", hint).strip("-") or f"subtitle-{index}"
    extension = _extension(url, _SUBTITLE_EXTENSIONS, ".vtt")
    return video_path.with_suffix(f".{safe_hint}{extension}")
