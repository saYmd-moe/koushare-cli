from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from . import __version__
from .errors import DownloadError


HTTP_HEADERS = {
    "Referer": "https://www.koushare.com/",
    "Origin": "https://www.koushare.com",
    "User-Agent": f"Mozilla/5.0 (compatible; koushare-cli/{__version__})",
}


def find_backend(requested: str = "auto") -> str:
    requested = requested.lower()
    if requested not in {"auto", "ffmpeg", "yt-dlp"}:
        raise DownloadError(f"unknown backend: {requested}")
    if requested != "auto":
        if shutil.which(requested) is None:
            raise DownloadError(f"{requested} was requested but is not in PATH")
        return requested
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    if shutil.which("yt-dlp"):
        return "yt-dlp"
    raise DownloadError("neither ffmpeg nor yt-dlp is installed")


def backend_status() -> dict[str, dict[str, str | bool | None]]:
    return {
        name: {"found": bool(path := shutil.which(name)), "path": path}
        for name in ("ffmpeg", "yt-dlp")
    }


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "…" if parts.query else "", ""))


def download_media(
    url: str,
    output: Path,
    *,
    backend: str = "auto",
    overwrite: bool = False,
    quiet: bool = False,
) -> str:
    output.parent.mkdir(parents=True, exist_ok=True)
    selected = find_backend(backend)

    if selected == "ffmpeg":
        header_blob = "".join(f"{k}: {v}\r\n" for k, v in HTTP_HEADERS.items())
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error" if quiet else "warning",
        ]
        if quiet:
            command.append("-nostats")
        else:
            command.append("-stats")
        command.extend(
            [
                "-y" if overwrite else "-n",
                "-headers",
                header_blob,
                "-i",
                url,
                "-map",
                "0",
                "-c",
                "copy",
                str(output),
            ]
        )
    else:
        command = ["yt-dlp", "--no-part"]
        if quiet:
            command.extend(["--quiet", "--no-warnings"])
        if overwrite:
            command.append("--force-overwrites")
        for key, value in HTTP_HEADERS.items():
            command.extend(["--add-header", f"{key}:{value}"])
        command.extend(["-o", str(output), url])

    try:
        if quiet:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        else:
            subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        detail = ""
        if quiet:
            captured = (exc.stderr or exc.stdout or "").strip()
            if captured:
                detail = captured.splitlines()[-1][:500]
        suffix = f": {detail}" if detail else ""
        raise DownloadError(f"{selected} exited with code {exc.returncode}{suffix}") from exc
    return selected
