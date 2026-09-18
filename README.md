# koushare-cli

A small command-line tool for inspecting and downloading **Koushare / 蔻享学术**
videos and live replays that you can normally access. It is intentionally useful
both from an interactive shell and from coding agents.

The project combines two useful ideas from existing tools:

- the **current** `api-core.koushare.com` API/signing approach used by
  [DouyinGo](https://github.com/cacity/DouyinGo);
- the focused CLI and legacy live/replay workflow of
  [KouShare-dl](https://github.com/yliu7949/KouShare-dl).

Unlike DouyinGo, this project has no GUI. Unlike the older KouShare-dl API path,
it understands current URLs such as:

```text
https://www.koushare.com/live/details/LIVE_ID
https://www.koushare.com/live/details/LIVE_ID?vid=VIDEO_ID
https://www.koushare.com/video/details/VIDEO_ID
```

In every example below, replace `LIVE_ID`, `VIDEO_ID`, and `ROOM_ID` with IDs
from a Koushare page you are authorized to access.

A `live/details/<id>` URL **does not need a `vid`**. `ksdl` can list all replay
videos attached to that page and then select one or download all of them.
Normal replay entries and the site's newer “fast playback” entries are detected
through their respective APIs and presented through the same commands.

## Install

Python 3.10+ is required. For actual downloads, install either `ffmpeg`
(recommended) or `yt-dlp`.

```bash
# Linux (Arch example)
sudo pacman -S ffmpeg python-pipx
pipx install .

# macOS
brew install ffmpeg pipx
pipx install .
```

Windows PowerShell, after installing Python and FFmpeg with your preferred
package manager:

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
pipx install .
```

Installing directly from GitHub works on Linux, macOS, and Windows:

```bash
pipx install 'git+https://github.com/saYmd-moe/koushare-cli.git'
```

Upgrade or uninstall through the same tool:

```bash
pipx upgrade koushare-cli
pipx uninstall koushare-cli
```

For development:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

Check the installation:

```bash
ksdl doctor
ksdl doctor --json
```

## Basic usage

Inspect a live page and list its attached replay videos:

```bash
ksdl list 'https://www.koushare.com/live/details/LIVE_ID'
ksdl list 'https://www.koushare.com/live/details/LIVE_ID' --json
```

Get metadata:

```bash
ksdl info 'https://www.koushare.com/live/details/LIVE_ID'
ksdl info 'https://www.koushare.com/live/details/LIVE_ID?vid=VIDEO_ID' --json
```

Download one replay when the URL already contains `vid`:

```bash
ksdl download 'https://www.koushare.com/live/details/LIVE_ID?vid=VIDEO_ID'
```

Choose a replay from a page that contains several videos:

```bash
ksdl download 'https://www.koushare.com/live/details/LIVE_ID' --video-id VIDEO_ID
```

Download every replay attached to that live page:

```bash
ksdl download 'https://www.koushare.com/live/details/LIVE_ID' --all --dir ./downloads
```

Choose quality and backend:

```bash
ksdl download URL -q 720p --backend ffmpeg
ksdl download URL -q best --backend yt-dlp
```

## Output paths and filenames

There are three intentionally distinct output modes.

### 1. Exact output path

Best for agents and scripts when the final path is already known:

```bash
ksdl download URL --video-id VIDEO_ID \
  --path '/data/koushare/special-name.mp4'
```

`--path` only works when exactly one video is selected.

### 2. Directory + literal name

```bash
ksdl download URL --video-id VIDEO_ID \
  --dir '/data/koushare' \
  --name 'special lecture.mp4'
```

If the name has no extension, `.mp4` is added.

### 3. Directory + metadata template

This is the preferred mode for batches:

```bash
ksdl download URL --all \
  --dir '/data/koushare/event' \
  --template '{index:02d} - {speaker} - {title} [{video_id}].{ext}'
```

Available canonical fields are:

```text
title       video_id    id          live_id
room_id     live_title  quality     height
index       date        speaker     ext
```

`index` is numeric, so normal Python format specifications such as
`{index:02d}` work. `speaker` and `date` depend on whether Koushare exposes those
fields for that video.

The default template is:

```text
{title} [{video_id}].{ext}
```

Filename-invalid path characters are sanitized. Directory separators belong in
`--dir` or `--path`, not inside `--name` or `--template`.

Preview the exact filenames and paths before downloading:

```bash
ksdl plan URL --all --dir ./downloads \
  --template '{index:02d} - {title} [{video_id}]' --json
```

The plan also exposes `name_context`, which is useful when designing templates.

`-o/--output` remains accepted as a compatibility alias for `--dir`.

## Agent-friendly operation

Commands that an agent will consume support `--json`. In particular:

```bash
ksdl list URL --json
ksdl info URL --json
ksdl plan URL --video-id VIDEO_ID --dir /data --json
ksdl download URL --video-id VIDEO_ID --dir /data --skip-existing --json
```

A successful download returns a stable object like:

```json
{
  "ok": true,
  "downloads": [
    {
      "status": "downloaded",
      "video_id": "VIDEO_ID",
      "live_id": "LIVE_ID",
      "room_id": null,
      "title": "Example talk",
      "quality": "FHD",
      "height": 1080,
      "path": "/data/Example talk [VIDEO_ID].mp4",
      "backend": "ffmpeg"
    }
  ]
}
```

Known failures exit with status `2`. When `--json` is active, the error is
written to stderr as JSON. `Ctrl-C` exits with `130`.

For repeatable agent workflows, use `--skip-existing`. Use `--overwrite` only
when replacement is intentional.

Write a metadata sidecar without persisting the signed media URL:

```bash
ksdl download URL --video-id VIDEO_ID --dir /data \
  --skip-existing --write-info-json --json
```

This creates `video.mp4.info.json` next to the media file.

## Resolve without downloading

```bash
ksdl resolve URL -q best
ksdl resolve 'https://www.koushare.com/live/details/LIVE_ID' --all --json
```

`resolve` returns the actual media URL and therefore can expose a signed URL.
For normal automation, prefer `plan` or `download`.

A non-downloading preview that redacts media query strings is also available:

```bash
ksdl download URL --dry-run --json
```

## Explicit IDs

```bash
ksdl list live:LIVE_ID
ksdl info video:VIDEO_ID
ksdl info room:ROOM_ID
```

A bare integer is treated as a current **live id**.

## Authentication

Log in once with the same phone number or email and password you use on the
Koushare website:

```bash
ksdl auth login --username 'person@example.com'
```

The password is read by a hidden terminal prompt. Phone accounts default to
country code `86`:

```bash
ksdl auth login --username '13800138000' --area-code 86
```

For a non-interactive agent or script, pass the password over stdin rather than
putting it in the process arguments:

```bash
printf '%s\n' "$KOUSHARE_PASSWORD" |
  ksdl auth login --username "$KOUSHARE_USERNAME" --password-stdin --json
```

The password is sent only to Koushare's account-login endpoint and is never
saved. The returned access and refresh tokens are stored in the operating
system's standard per-user configuration directory:

```text
Linux:   $XDG_CONFIG_HOME/koushare-cli/auth.json
         or ~/.config/koushare-cli/auth.json
macOS:   ~/Library/Application Support/koushare-cli/auth.json
Windows: %LOCALAPPDATA%\koushare-cli\auth.json
```

On POSIX systems the file is written with mode `0600`. Windows uses the normal
per-user AppData ACLs instead of emulating Unix mode bits. Override the complete
path on any platform with `KOUSHARE_AUTH_FILE`.

Inspect or remove the saved login with:

```bash
ksdl auth status --json
ksdl auth logout --json
```

Normal commands load the saved access token automatically. When it expires,
`ksdl` uses the saved refresh token to obtain and atomically persist a new token
pair. It also sends the current web client's `Client`, `Ks-Sign`, and
`Ks-Timestamp` headers and uses the V2 video authorization/playback endpoints.

For backwards compatibility, `KOUSHARE_TOKEN` and `--token` still override the
saved login. The value is the web client's raw access token; do not add a
`Bearer ` prefix.

Old `/lives/room/<roomId>` links use a separate legacy API. For an old account
cookie, use `KOUSHARE_LEGACY_TOKEN`. Password-protected rooms accept a password
you already possess via `--password`.

`koushare-cli` does **not** attempt to defeat DRM, guess room passwords, bypass
payment/access controls, or obtain content your account cannot normally view.

## Agent Skill

The repository includes a standard Agent Skill at:

```text
skills/koushare-cli/SKILL.md
```

Pi can discover skills from `~/.agents/skills/` or `~/.pi/agent/skills/`. From a
clone of this repository, install a symlink into the cross-agent location with:

```bash
./scripts/install-skill.sh
```

which creates:

```text
~/.agents/skills/koushare-cli -> <this repo>/skills/koushare-cli
```

You can also choose another destination explicitly:

```bash
./scripts/install-skill.sh ~/.pi/agent/skills/koushare-cli
```

On Windows PowerShell, use the copy-based installer, which does not require
Developer Mode or permission to create symbolic links:

```powershell
.\scripts\install-skill.ps1
```

Both installers refuse to overwrite an existing Skill directory.

The skill instructs an agent to use `list -> plan -> download`, prefer JSON,
avoid silent selection when a live page contains several talks, use deterministic
filename templates, and keep credentials/signed media URLs out of logs.

## Commands

```text
ksdl auth login --username ACCOUNT [--area-code CODE] [--password-stdin] [--json]
ksdl auth status [--json]
ksdl auth logout [--json]
ksdl doctor [--json]
ksdl list TARGET [--json]
ksdl info TARGET [--video-id ID] [--json]
ksdl resolve TARGET [--video-id ID | --all] [-q QUALITY] [--json]
ksdl plan TARGET [--video-id ID | --all] [-q QUALITY]
          [--path FILE | --dir DIR [--name FILE | --template TEMPLATE]] [--json]
ksdl download TARGET [--video-id ID | --all] [-q QUALITY]
              [--path FILE | --dir DIR [--name FILE | --template TEMPLATE]]
              [--skip-existing | --overwrite] [--write-info-json] [--json]
```

Run `ksdl COMMAND --help` for all options.

## Why another downloader?

The older KouShare-dl remains a neat small CLI, but much of its API integration
predates the current site. DouyinGo has the newer API logic, but Koushare is only
one feature inside a much larger desktop application. This repository keeps the
modern resolver while returning to a small Unix-like CLI.

## Status

This is a `0.3.0` implementation. The request signing and endpoint layout are
based on the current open-source client behavior as of September 2026. Koushare
can change its private web API at any time.

The included unit tests validate URL parsing, signing, quality selection,
metadata-based naming, and agent-oriented JSON/planning behavior. They do not
hit Koushare's production servers.

## License

MIT. See `LICENSE` and `THIRD_PARTY_NOTICES.md`.
