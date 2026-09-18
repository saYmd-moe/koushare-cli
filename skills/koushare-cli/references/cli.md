# ksdl command reference for agents

## Authentication

```bash
ksdl auth login --username ACCOUNT [--area-code 86] [--password-stdin] [--json]
ksdl auth status [--json]
ksdl auth logout [--json]
```

Interactive login prompts without echoing the password. For automation, use
`--password-stdin`. The password is not persisted; access and refresh tokens are
stored in the platform-standard private config directory and refreshed
automatically. `KOUSHARE_AUTH_FILE` overrides the complete path.

## Targets

Accepted target forms include:

```text
https://www.koushare.com/live/details/LIVE_ID
https://www.koushare.com/live/details/LIVE_ID?vid=VIDEO_ID
https://www.koushare.com/video/details/VIDEO_ID
live:LIVE_ID
video:VIDEO_ID
room:ROOM_ID
LIVE_ID
```

A bare integer is interpreted as a current live ID.

## Stable commands

### Environment check

```bash
ksdl doctor --json
```

Returns package/Python version, backend availability, and booleans indicating whether token environment variables are present. It never prints token values.

### List a live page

```bash
ksdl list TARGET --json
```

Shape:

```json
{
  "live_id": "LIVE_ID",
  "title": "...",
  "videos": [
    {
      "video_id": "VIDEO_ID",
      "title": "...",
      "metadata": {}
    }
  ],
  "metadata": {}
}
```

### Inspect metadata

```bash
ksdl info TARGET --json
ksdl info TARGET --video-id VIDEO_ID --json
```

### Resolve a media URL

```bash
ksdl resolve TARGET --video-id VIDEO_ID -q best --json
```

This can expose a signed media URL. Do not use it merely to download a file.

### Plan filenames and output locations

```bash
ksdl plan TARGET --video-id VIDEO_ID --path '/data/talk.mp4' --json
ksdl plan TARGET --all --dir '/data/event' --template '{index:02d} - {title} [{video_id}]' --json
```

A plan redacts query strings in `media_url` and returns `name_context` for template debugging.

### Download

Single exact path:

```bash
ksdl download TARGET --video-id VIDEO_ID \
  --path '/data/talk.mp4' --skip-existing --write-info-json --json
```

Single literal name:

```bash
ksdl download TARGET --video-id VIDEO_ID \
  --dir '/data' --name 'special lecture.mp4' --skip-existing --json
```

Batch metadata naming:

```bash
ksdl download TARGET --all --dir '/data/event' \
  --template '{index:02d} - {speaker} - {title} [{video_id}].{ext}' \
  --skip-existing --write-info-json --json
```

Successful JSON shape:

```json
{
  "ok": true,
  "downloads": [
    {
      "status": "downloaded",
      "video_id": "VIDEO_ID",
      "live_id": "LIVE_ID",
      "room_id": null,
      "title": "...",
      "quality": "FHD",
      "height": 1080,
      "path": "/absolute/path/file.mp4",
      "backend": "ffmpeg",
      "info_json": "/absolute/path/file.mp4.info.json"
    }
  ]
}
```

`status` can be `downloaded`, `skipped`, or `dry-run`.

## Selection

For a live page containing several videos, `download` and `plan` intentionally fail unless one of these is supplied:

```text
--video-id ID
--all
```

This prevents an agent from silently downloading the wrong talk.

## Quality

Accepted common values:

```text
best
FHD / 1080p
HD / 720p
SD / 480p
```

If the requested tier is absent, `ksdl` falls back to another available tier.

## Naming

Default:

```text
{title} [{video_id}].{ext}
```

Available canonical template fields:

```text
title
video_id
id
live_id
room_id
live_title
quality
height
index
date
speaker
ext
```

`index` is an integer, so format specifications work:

```text
{index:02d}
```

Optional metadata fields such as `speaker` and `date` can be empty. Run `plan --json` and inspect `name_context` when their presence matters.

## Existing files

Default behavior is conservative and does not overwrite. For repeatable agent workflows, prefer:

```text
--skip-existing
```

Use `--overwrite` only when the user explicitly wants replacement.

## Metadata sidecars

`--write-info-json` writes `<video>.mp4.info.json`. The sidecar contains normalized download metadata plus Koushare metadata used for naming. It intentionally does not persist the signed playback URL.

`--write-sidecars` also saves the available cover, HTML description, and subtitle/caption files. Use `--write-cover`, `--write-description`, or `--write-subs` to request them individually. Optional assets that are not exposed by Koushare are skipped without failing the video download.

## Exit codes

```text
0    success, including --skip-existing
2    known CLI/API/download/setup error
130  interrupted
```

With `--json`, known errors are emitted to stderr as:

```json
{"ok": false, "error": "...", "type": "ApiError"}
```
