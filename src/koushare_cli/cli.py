from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import __version__
from .api import KoushareClient, available_qualities, choose_media
from .assets import (
    cover_path,
    cover_url,
    description_html,
    download_asset,
    subtitle_path,
    subtitle_urls,
)
from .auth import CredentialStore
from .downloader import backend_status, download_media, redact_url
from .errors import ApiError, DownloadError, KoushareError
from .legacy import LegacyClient
from .naming import DEFAULT_TEMPLATE, build_name_context, literal_filename, render_filename
from .urls import Target, parse_target


@dataclass
class ResolvedVideo:
    video_id: str
    title: str
    playback: dict[str, Any]
    live_id: str | None = None
    item: dict[str, Any] | None = None
    live_info: dict[str, Any] | None = None


def _video_id(item: dict[str, Any]) -> str:
    for key in ("videoId", "vid", "id"):
        value = item.get(key)
        if value is not None and str(value):
            return str(value)
    return ""


def _video_title(item: dict[str, Any], fallback: str) -> str:
    for key in ("title", "name", "videoTitle", "topicName", "ltitle"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _normalized_playback_item(item: dict[str, Any]) -> dict[str, Any]:
    ident = _video_id(item)
    return {
        "video_id": ident,
        "title": _video_title(item, f"koushare_{ident}" if ident else "(untitled)"),
        "metadata": item,
    }


def _is_fastback(item: dict[str, Any]) -> bool:
    return item.get("isFastBack") is True


def _live_listing(live_id: str, info: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "live_id": live_id,
        "title": _video_title(info, f"live {live_id}"),
        "videos": [_normalized_playback_item(item) for item in items],
        "metadata": info,
    }


def _print_playbacks(items: list[dict[str, Any]]) -> None:
    if not items:
        print("No replay videos found.")
        return
    width = max(8, min(16, max(len(_video_id(x)) for x in items)))
    print(f"{'video id':<{width}}  title")
    print(f"{'-' * width}  {'-' * 60}")
    for item in items:
        ident = _video_id(item) or "?"
        title = _video_title(item, "(untitled)")
        print(f"{ident:<{width}}  {title}")


def _client(args: argparse.Namespace) -> KoushareClient:
    authorization = args.token or os.getenv("KOUSHARE_TOKEN")
    store = CredentialStore()
    credentials = None if authorization else store.load()
    return KoushareClient(
        authorization=authorization,
        credentials=credentials,
        credential_store=store if credentials else None,
        api_base=args.api_base,
        timeout=args.timeout,
    )


def _legacy_client(args: argparse.Namespace) -> LegacyClient:
    return LegacyClient(token=args.legacy_token or os.getenv("KOUSHARE_LEGACY_TOKEN"), timeout=args.timeout)


def _resolve_current(
    client: KoushareClient,
    target: Target,
    *,
    video_id_override: str | None = None,
    all_videos: bool = False,
) -> list[ResolvedVideo]:
    if target.kind == "video":
        assert target.video_id
        ticket = target.ticket or ""
        info = client.video_info_v2(target.video_id)
        free_urls = info.get("freeUrlList")
        if not client.is_authenticated and not ticket and isinstance(free_urls, list) and free_urls:
            playback = {"playbackUrls": free_urls}
        else:
            access = client.video_access(target.video_id, ticket=ticket)
            secret = access.get("secret")
            if secret:
                info = client.video_info_v2(target.video_id, secret=str(secret))
            playback = client.video_playback_v2(target.video_id, ticket=ticket)
        title = _video_title(info, f"koushare_{target.video_id}")
        return [ResolvedVideo(target.video_id, title, playback, item=info)]

    if target.kind != "live" or not target.live_id:
        raise ApiError("target is not a current Koushare live/video URL")

    live_info = client.live_info(target.live_id)
    selected_video = video_id_override or target.video_id
    items = client.live_playbacks(target.live_id)
    if selected_video:
        match = next((x for x in items if _video_id(x) == str(selected_video)), {})
        fallback = _video_title(live_info, f"koushare_{selected_video}")
        title = _video_title(match, fallback)
        return [
            ResolvedVideo(
                str(selected_video),
                title,
                client.live_playback(
                    target.live_id,
                    str(selected_video),
                    fastback=_is_fastback(match),
                ),
                live_id=target.live_id,
                item=match,
                live_info=live_info,
            )
        ]

    if not items:
        raise ApiError("this live page currently exposes no replay videos")
    if len(items) > 1 and not all_videos:
        ids = ", ".join(_video_id(x) for x in items[:8] if _video_id(x))
        raise ApiError(
            f"this live page contains {len(items)} replay videos ({ids}). "
            "Use --all or --video-id <id>."
        )

    selected = items if all_videos else items[:1]
    resolved: list[ResolvedVideo] = []
    for item in selected:
        vid = _video_id(item)
        if not vid:
            continue
        title = _video_title(item, f"koushare_{vid}")
        resolved.append(
            ResolvedVideo(
                vid,
                title,
                client.live_playback(target.live_id, vid, fastback=_is_fastback(item)),
                live_id=target.live_id,
                item=item,
                live_info=live_info,
            )
        )
    if not resolved:
        raise ApiError("replay list did not contain usable video ids")
    return resolved


def _download_output_dir(args: argparse.Namespace) -> Path:
    value = getattr(args, "output_dir", None) or "."
    return Path(value).expanduser().resolve()


def _validate_output_args(args: argparse.Namespace, count: int) -> None:
    if getattr(args, "path", None):
        if count != 1:
            raise KoushareError("--path requires exactly one selected video; use --dir/--template with --all")
        if getattr(args, "output_dir", None) or getattr(args, "name", None) or getattr(args, "template", None):
            raise KoushareError("--path cannot be combined with --dir/--output, --name, or --template")
    if getattr(args, "name", None) and count != 1:
        raise KoushareError("--name requires exactly one selected video; use --template for multiple videos")
    if getattr(args, "name", None) and getattr(args, "template", None):
        raise KoushareError("--name and --template are mutually exclusive")


def _height(media_item: dict[str, Any]) -> int | str | None:
    value = media_item.get("height")
    if value is None:
        return None
    if isinstance(value, (int, str)):
        return value
    return str(value)


def _planned_rows(
    resolved: list[ResolvedVideo],
    args: argparse.Namespace,
    *,
    source: str,
) -> list[dict[str, Any]]:
    _validate_output_args(args, len(resolved))
    output_dir = _download_output_dir(args)
    rows: list[dict[str, Any]] = []

    for index, video in enumerate(resolved, start=1):
        url, media_item = choose_media(video.playback, args.quality)
        quality = str(media_item.get("labelEn") or media_item.get("label") or args.quality)
        context = build_name_context(
            title=video.title,
            video_id=video.video_id,
            live_id=video.live_id,
            quality=quality,
            height=_height(media_item),
            index=index,
            item=video.item,
            live_info=video.live_info,
        )

        if getattr(args, "path", None):
            output = Path(args.path).expanduser().resolve()
            if not output.suffix:
                output = output.with_suffix(".mp4")
        else:
            if getattr(args, "name", None):
                filename = literal_filename(args.name, fallback=f"koushare_{video.video_id}")
            else:
                template = getattr(args, "template", None) or DEFAULT_TEMPLATE
                filename = render_filename(template, context, fallback=f"koushare_{video.video_id}")
            output = output_dir / filename

        rows.append(
            {
                "video_id": video.video_id,
                "live_id": video.live_id,
                "title": video.title,
                "quality": quality,
                "height": _height(media_item),
                "path": str(output),
                "source": source,
                "url": url,
                "name_context": context,
                "metadata": video.item or {},
                "live_metadata": video.live_info or {},
            }
        )
    return rows


def _legacy_plan(target: Target, args: argparse.Namespace, *, source: str) -> list[dict[str, Any]]:
    assert target.room_id
    data = _legacy_client(args).room_info(target.room_id, password=args.password)
    url = data.get("hlsurl") or data.get("bqhlsurl") or data.get("lnoticeurl")
    if not isinstance(url, str) or not url:
        raise ApiError("legacy room did not expose a downloadable HLS URL")
    title = _video_title(data, f"room_{target.room_id}")
    context = build_name_context(
        title=title,
        video_id=target.room_id,
        room_id=target.room_id,
        quality=args.quality,
        index=1,
        item=data,
        live_info=data,
    )
    _validate_output_args(args, 1)
    if getattr(args, "path", None):
        output = Path(getattr(args, "path")).expanduser().resolve()
        if not output.suffix:
            output = output.with_suffix(".mp4")
    else:
        if getattr(args, "name", None):
            filename = literal_filename(args.name, fallback=f"room_{target.room_id}")
        else:
            template = getattr(args, "template", None) or "{title} [room-{room_id}].{ext}"
            filename = render_filename(template, context, fallback=f"room_{target.room_id}")
        output = _download_output_dir(args) / filename
    return [
        {
            "video_id": target.room_id,
            "room_id": target.room_id,
            "live_id": None,
            "title": title,
            "quality": args.quality,
            "height": None,
            "path": str(output),
            "source": source,
            "url": url,
            "name_context": context,
            "metadata": data,
            "live_metadata": data,
        }
    ]


def _make_plan(args: argparse.Namespace) -> list[dict[str, Any]]:
    target = parse_target(args.target)
    if target.kind == "legacy-room":
        return _legacy_plan(target, args, source=args.target)
    resolved = _resolve_current(
        _client(args),
        target,
        video_id_override=args.video_id,
        all_videos=args.all,
    )
    return _planned_rows(resolved, args, source=args.target)


def cmd_list(args: argparse.Namespace) -> int:
    target = parse_target(args.target)
    if target.kind != "live" or not target.live_id:
        raise KoushareError("list expects a current live/details URL or live:<id>")
    client = _client(args)
    info = client.live_info(target.live_id)
    items = client.live_playbacks(target.live_id)
    if args.json:
        print(json.dumps(_live_listing(target.live_id, info, items), ensure_ascii=False, indent=2))
    else:
        title = _video_title(info, f"live {target.live_id}")
        print(f"{title} (live id: {target.live_id})")
        _print_playbacks(items)
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    target = parse_target(args.target)
    if target.kind == "legacy-room":
        data = _legacy_client(args).room_info(target.room_id or "", password=args.password)
        result = {
            "kind": "legacy-room",
            "room_id": target.room_id,
            "title": _video_title(data, f"room {target.room_id}"),
            "metadata": data,
        }
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result["title"])
            for key in ("livedate", "lsponsor", "topicname", "islive", "playback"):
                if data.get(key) not in (None, ""):
                    print(f"{key}: {data[key]}")
        return 0

    client = _client(args)
    if target.kind == "live" and target.live_id and not target.video_id and not args.video_id:
        info = client.live_info(target.live_id)
        items = client.live_playbacks(target.live_id)
        if args.json:
            print(json.dumps(_live_listing(target.live_id, info, items), ensure_ascii=False, indent=2))
        else:
            print(f"{_video_title(info, f'live {target.live_id}')} (live id: {target.live_id})")
            _print_playbacks(items)
        return 0

    resolved = _resolve_current(client, target, video_id_override=args.video_id)
    video = resolved[0]
    data = {
        "kind": "video",
        "video_id": video.video_id,
        "live_id": video.live_id,
        "title": video.title,
        "qualities": available_qualities(video.playback),
        "metadata": video.item or {},
        "live_metadata": video.live_info or {},
    }
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(video.title)
        print(f"video id: {video.video_id}")
        qualities = data["qualities"]
        print("qualities: " + (", ".join(qualities) if qualities else "unknown"))
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    target = parse_target(args.target)
    if target.kind == "legacy-room":
        rows = _legacy_plan(target, args, source=args.target)
        result = {
            "room_id": target.room_id,
            "title": rows[0]["title"],
            "quality": rows[0]["quality"],
            "url": rows[0]["url"],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result["url"])
        return 0

    client = _client(args)
    rows = []
    for video in _resolve_current(
        client,
        target,
        video_id_override=args.video_id,
        all_videos=args.all,
    ):
        url, item = choose_media(video.playback, args.quality)
        rows.append(
            {
                "video_id": video.video_id,
                "live_id": video.live_id,
                "title": video.title,
                "quality": item.get("labelEn") or item.get("label") or args.quality,
                "height": _height(item),
                "url": url,
            }
        )
    if args.json or len(rows) > 1:
        print(json.dumps(rows if len(rows) > 1 else rows[0], ensure_ascii=False, indent=2))
    else:
        print(rows[0]["url"])
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    rows = _make_plan(args)
    public_rows = []
    for row in rows:
        public_rows.append(
            {
                "video_id": row["video_id"],
                "live_id": row.get("live_id"),
                "room_id": row.get("room_id"),
                "title": row["title"],
                "quality": row["quality"],
                "height": row["height"],
                "path": row["path"],
                "media_url": redact_url(row["url"]),
                "name_context": row["name_context"],
            }
        )
    if args.json:
        print(json.dumps({"ok": True, "items": public_rows}, ensure_ascii=False, indent=2))
    else:
        for row in public_rows:
            print(row["path"])
            print(f"  video_id={row['video_id']} quality={row['quality']} {row['media_url']}")
    return 0


def _write_info_sidecar(row: dict[str, Any], status: str, backend: str | None) -> str:
    path = Path(row["path"])
    sidecar = path.with_suffix(path.suffix + ".info.json")
    payload = {
        "video_id": row["video_id"],
        "live_id": row.get("live_id"),
        "room_id": row.get("room_id"),
        "title": row["title"],
        "quality": row["quality"],
        "height": row["height"],
        "path": row["path"],
        "source": row["source"],
        "status": status,
        "backend": backend,
        "name_context": row["name_context"],
        "metadata": row["metadata"],
        "live_metadata": row["live_metadata"],
    }
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(sidecar)


def _write_requested_sidecars(row: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    video_path = Path(row["path"])
    metadata = row["metadata"]
    live_metadata = row["live_metadata"]
    result: dict[str, Any] = {}

    if args.write_cover or args.write_sidecars:
        url = cover_url(metadata, live_metadata)
        if url:
            result["cover"] = str(download_asset(url, cover_path(video_path, url), timeout=args.timeout))

    if args.write_description or args.write_sidecars:
        description = description_html(metadata, live_metadata)
        if description:
            path = video_path.with_suffix(".description.html")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(description, encoding="utf-8")
            result["description"] = str(path)

    if args.write_subs or args.write_sidecars:
        paths: list[str] = []
        for index, (hint, url) in enumerate(subtitle_urls(metadata, live_metadata), start=1):
            path = subtitle_path(video_path, hint, url, index)
            paths.append(str(download_asset(url, path, timeout=args.timeout)))
        if paths:
            result["subtitles"] = paths

    return result


def cmd_download(args: argparse.Namespace) -> int:
    rows = _make_plan(args)
    results: list[dict[str, Any]] = []

    for row in rows:
        output = Path(row["path"])
        status = "planned" if args.dry_run else "downloaded"
        selected_backend: str | None = None
        sidecars: dict[str, Any] = {}

        if args.dry_run:
            status = "dry-run"
        elif output.exists() and args.skip_existing:
            status = "skipped"
        else:
            if not args.json:
                print(f"Downloading: {row['title']} [{row['quality']}] -> {output}")
            selected_backend = download_media(
                row["url"],
                output,
                backend=args.backend,
                overwrite=args.overwrite,
                quiet=args.json or args.quiet,
            )

        if status != "dry-run":
            if args.write_info_json or args.write_sidecars:
                sidecars["info_json"] = _write_info_sidecar(row, status, selected_backend)
            sidecars.update(_write_requested_sidecars(row, args))

        result = {
            "status": status,
            "video_id": row["video_id"],
            "live_id": row.get("live_id"),
            "room_id": row.get("room_id"),
            "title": row["title"],
            "quality": row["quality"],
            "height": row["height"],
            "path": str(output),
            "backend": selected_backend,
        }
        result.update(sidecars)
        results.append(result)

        if not args.json and args.dry_run:
            print(f"{output}\n  quality={row['quality']}  {redact_url(row['url'])}")
        elif not args.json and status == "skipped":
            print(f"Skipped existing: {output}")
        elif not args.json and not args.dry_run:
            print(output)

    if args.json:
        print(json.dumps({"ok": True, "downloads": results}, ensure_ascii=False, indent=2))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    backends = backend_status()
    ready = any(bool(value["found"]) for value in backends.values())
    result = {
        "ok": ready,
        "version": __version__,
        "python": sys.version.split()[0],
        "download_ready": ready,
        "backends": backends,
        "environment": {
            "KOUSHARE_TOKEN": bool(os.getenv("KOUSHARE_TOKEN")),
            "KOUSHARE_LEGACY_TOKEN": bool(os.getenv("KOUSHARE_LEGACY_TOKEN")),
        },
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"koushare-cli {__version__}")
        print(f"Python {result['python']}")
        for name, value in backends.items():
            print(f"{name}: {value['path'] if value['found'] else 'not found'}")
        print("download ready" if ready else "no download backend found")
    return 0 if ready else 2


def cmd_auth_login(args: argparse.Namespace) -> int:
    password = os.getenv("KOUSHARE_PASSWORD")
    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    elif password is None:
        if not sys.stdin.isatty():
            raise KoushareError(
                "no interactive terminal for password; use --password-stdin or KOUSHARE_PASSWORD"
            )
        password = getpass.getpass("Koushare password: ")
    credentials = KoushareClient.login(
        args.username,
        password,
        area_code=args.area_code,
        api_base=args.api_base,
        timeout=args.timeout,
    )
    store = CredentialStore()
    store.save(credentials)
    result = {
        "ok": True,
        "authenticated": True,
        "username": credentials.username,
        "auth_file": str(store.path),
        "access_expires_at": credentials.access_expires_at,
        "refresh_expires_at": credentials.refresh_expires_at,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Logged in as {credentials.username}; credentials saved to {store.path}")
    return 0


def cmd_auth_status(args: argparse.Namespace) -> int:
    store = CredentialStore()
    credentials = store.load()
    if credentials and credentials.access_expired() and not credentials.refresh_expired():
        client = KoushareClient(
            credentials=credentials,
            credential_store=store,
            api_base=args.api_base,
            timeout=args.timeout,
        )
        credentials = client.refresh_auth()
    result = {
        "ok": credentials is not None and not credentials.refresh_expired(),
        "authenticated": credentials is not None and not credentials.refresh_expired(),
        "username": credentials.username if credentials else None,
        "auth_file": str(store.path),
        "access_expired": credentials.access_expired() if credentials else None,
        "refresh_expired": credentials.refresh_expired() if credentials else None,
        "access_expires_at": credentials.access_expires_at if credentials else None,
        "refresh_expires_at": credentials.refresh_expires_at if credentials else None,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif credentials:
        state = "ready" if result["authenticated"] else "expired"
        print(f"Authentication: {state} ({credentials.username or 'unknown account'})")
        print(f"Credential file: {store.path}")
    else:
        print("Authentication: not logged in")
    return 0 if result["authenticated"] else 1


def cmd_auth_logout(args: argparse.Namespace) -> int:
    store = CredentialStore()
    removed = store.clear()
    result = {"ok": True, "authenticated": False, "removed": removed, "auth_file": str(store.path)}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("Saved Koushare credentials removed." if removed else "No saved Koushare credentials.")
    return 0


def _add_selection_options(parser: argparse.ArgumentParser) -> None:
    pick = parser.add_mutually_exclusive_group()
    pick.add_argument("--video-id")
    pick.add_argument("--all", action="store_true", help="operate on every replay attached to a live page")


def _add_download_path_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-O",
        "--path",
        help="exact output file path; valid only when exactly one video is selected",
    )
    parser.add_argument(
        "-d",
        "--dir",
        "-o",
        "--output",
        dest="output_dir",
        help="output directory (default: current directory); -o/--output kept for compatibility",
    )
    parser.add_argument("-n", "--name", help="exact filename for a single selected video; .mp4 is added if omitted")
    parser.add_argument(
        "-t",
        "--template",
        help=(
            "filename template for one or many videos; fields: {title}, {video_id}, {live_id}, "
            "{room_id}, {live_title}, {quality}, {height}, {index}, {date}, {speaker}, {ext}"
        ),
    )


def _add_common_media_options(parser: argparse.ArgumentParser) -> None:
    _add_selection_options(parser)
    parser.add_argument("-q", "--quality", default="best", help="best/FHD/HD/SD or 1080p/720p/480p")
    parser.add_argument("--password", help="password for a legacy room when required")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ksdl",
        description="Inspect and download Koushare videos/replays you can normally access.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--token", help="Authorization header value; alternatively set KOUSHARE_TOKEN")
    parser.add_argument("--legacy-token", help="Token cookie value for old APIs; alternatively set KOUSHARE_LEGACY_TOKEN")
    parser.add_argument("--api-base", help=argparse.SUPPRESS)
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout in seconds (default: 20)")

    sub = parser.add_subparsers(dest="command", required=True)

    p_auth = sub.add_parser("auth", help="log in, inspect, or remove saved account credentials")
    auth_sub = p_auth.add_subparsers(dest="auth_command", required=True)
    p_auth_login = auth_sub.add_parser("login", help="log in with a phone number or email and save refreshable tokens")
    p_auth_login.add_argument("--username", required=True, help="Koushare phone number or email address")
    p_auth_login.add_argument("--area-code", default="86", help="phone country code without + (default: 86)")
    p_auth_login.add_argument(
        "--password-stdin",
        action="store_true",
        help="read one password line from stdin; otherwise prompt securely or use KOUSHARE_PASSWORD",
    )
    p_auth_login.add_argument("--json", action="store_true")
    p_auth_login.set_defaults(func=cmd_auth_login)

    p_auth_status = auth_sub.add_parser("status", help="show login state and refresh an expired access token")
    p_auth_status.add_argument("--json", action="store_true")
    p_auth_status.set_defaults(func=cmd_auth_status)

    p_auth_logout = auth_sub.add_parser("logout", help="delete locally saved tokens")
    p_auth_logout.add_argument("--json", action="store_true")
    p_auth_logout.set_defaults(func=cmd_auth_logout)

    p_list = sub.add_parser("list", help="list replay videos attached to a live page")
    p_list.add_argument("target", help="live/details URL, live:<id>, or bare live id")
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_info = sub.add_parser("info", help="show metadata without downloading")
    p_info.add_argument("target")
    p_info.add_argument("--video-id")
    p_info.add_argument("--password", help="password for a legacy room when required")
    p_info.add_argument("--json", action="store_true")
    p_info.set_defaults(func=cmd_info)

    p_resolve = sub.add_parser("resolve", help="resolve the media URL without downloading")
    p_resolve.add_argument("target")
    _add_common_media_options(p_resolve)
    p_resolve.add_argument("--json", action="store_true")
    p_resolve.set_defaults(func=cmd_resolve)

    p_plan = sub.add_parser("plan", help="resolve metadata and output paths without downloading")
    p_plan.add_argument("target")
    _add_common_media_options(p_plan)
    _add_download_path_options(p_plan)
    p_plan.add_argument("--json", action="store_true")
    p_plan.set_defaults(func=cmd_plan)

    p_download = sub.add_parser("download", aliases=["save"], help="download a video or live replay")
    p_download.add_argument("target")
    _add_common_media_options(p_download)
    _add_download_path_options(p_download)
    p_download.add_argument("--backend", choices=["auto", "ffmpeg", "yt-dlp"], default="auto")
    exists = p_download.add_mutually_exclusive_group()
    exists.add_argument("--overwrite", action="store_true", help="replace an existing output file")
    exists.add_argument("--skip-existing", action="store_true", help="treat an existing output file as success")
    p_download.add_argument("--write-info-json", action="store_true", help="write a metadata sidecar next to each downloaded file")
    p_download.add_argument("--write-cover", action="store_true", help="save the cover image next to each downloaded file")
    p_download.add_argument("--write-description", action="store_true", help="save the available introduction as HTML")
    p_download.add_argument("--write-subs", action="store_true", help="save subtitle/caption files exposed by Koushare, if any")
    p_download.add_argument(
        "--write-sidecars",
        action="store_true",
        help="save info JSON, cover, description, and any available subtitles",
    )
    p_download.add_argument("--dry-run", action="store_true", help="resolve selections and output paths but do not download")
    p_download.add_argument("--quiet", action="store_true", help="suppress downloader progress output")
    p_download.add_argument("--json", action="store_true", help="emit a machine-readable result; also suppress downloader progress")
    p_download.set_defaults(func=cmd_download)

    p_doctor = sub.add_parser("doctor", help="check whether a download backend is available")
    p_doctor.add_argument("--json", action="store_true")
    p_doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (KoushareError, ApiError, DownloadError) as exc:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(exc), "type": exc.__class__.__name__}, ensure_ascii=False), file=sys.stderr)
        else:
            print(f"ksdl: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": "interrupted", "type": "KeyboardInterrupt"}), file=sys.stderr)
        else:
            print("ksdl: interrupted", file=sys.stderr)
        return 130
