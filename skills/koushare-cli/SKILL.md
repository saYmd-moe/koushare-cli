---
name: koushare-cli
description: Inspect, select, plan, and download Koushare/蔻享学术 videos and live replays with the ksdl command-line tool. Use when the user gives a koushare.com URL or asks an agent to list replay videos, choose a lecture by title or video ID, save one or many accessible videos to a specified path, apply metadata-based filenames, or verify Koushare download tooling. Prefer machine-readable JSON and non-interactive commands.
license: MIT
compatibility: Requires koushare-cli (`ksdl`) on PATH, network access to Koushare, and ffmpeg or yt-dlp for actual downloads. Python 3.10+ is required when installing from source.
---

# Koushare CLI

Use `ksdl` non-interactively. Prefer `--json` whenever the result will be consumed by the agent.

## Workflow

1. If download capability is uncertain, run:

   ```bash
   ksdl doctor --json
   ```

2. Parse the user's Koushare target. For a `live/details/<id>` page without a specific `vid`, inspect the replay list before choosing anything:

   ```bash
   ksdl list 'URL' --json
   ```

   Read `videos[].video_id` and `videos[].title`. If the user's request identifies a title, select the matching `video_id`. If several plausible matches remain, report them rather than silently choosing one. Use `--all` only when the user asks for all replays.

3. Before a consequential batch download or when filenames matter, preview the resolved output paths:

   ```bash
   ksdl plan 'URL' --video-id ID --dir '/target/dir' --json
   ```

   For batches:

   ```bash
   ksdl plan 'URL' --all --dir '/target/dir' \
     --template '{index:02d} - {speaker} - {title} [{video_id}].{ext}' --json
   ```

4. Download with deterministic, idempotent options:

   ```bash
   ksdl download 'URL' --video-id ID \
     --path '/target/dir/exact-name.mp4' \
     --skip-existing --write-info-json --json
   ```

   For all replays:

   ```bash
   ksdl download 'URL' --all --dir '/target/dir' \
     --template '{index:02d} - {title} [{video_id}].{ext}' \
     --skip-existing --write-info-json --json
   ```

5. Treat exit code `0` as success. With `--json`, parse stdout for successful results. On known failures, `ksdl` exits with code `2` and writes a JSON error object to stderr.

## Output and naming rules

Choose exactly one output mode:

- `--path /full/path/file.mp4`: exact location for one selected video.
- `--dir DIR --name FILE`: directory plus a literal filename for one selected video.
- `--dir DIR --template TEMPLATE`: metadata-based naming, suitable for one or many videos.

Useful template fields are `{title}`, `{video_id}`, `{live_id}`, `{room_id}`, `{live_title}`, `{quality}`, `{height}`, `{index}`, `{date}`, `{speaker}`, and `{ext}`. Use `ksdl plan ... --json` to inspect the `name_context` before relying on optional fields such as `speaker` or `date`.

The default filename is `{title} [{video_id}].{ext}`. Filename-invalid path characters are sanitized. `--path` is the only option that should contain directory separators.

## Authentication and safety

Prefer environment variables over command-line credentials:

```bash
export KOUSHARE_TOKEN='Bearer ...'
export KOUSHARE_LEGACY_TOKEN='...'
```

Never print, log, or persist those credential values. `ksdl resolve` may expose a signed media URL, so use it only when the actual media URL is necessary. For ordinary downloads, prefer `download --json`, whose result does not include the signed media URL.

Only retrieve content the user can normally access. Do not attempt to bypass payment, passwords, DRM, or account authorization.

## Reference

For the complete command contract, naming examples, and JSON shapes, read [references/cli.md](references/cli.md).
