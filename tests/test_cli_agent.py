import json
from argparse import Namespace
from pathlib import Path

import koushare_cli.cli as cli


class FakeClient:
    def live_info(self, live_id):
        return {"title": "Physics Meeting", "startTime": "2026-09-18 09:00:00"}

    def live_playbacks(self, live_id):
        return [
            {"videoId": "101", "title": "First / Talk", "speakerName": "Alice"},
            {"videoId": "102", "title": "Second Talk", "speakerName": "Bob"},
        ]

    def live_playback(self, live_id, video_id, *, fastback=False):
        return {
            "playbackUrls": [
                {
                    "list": [
                        {
                            "labelEn": "FHD",
                            "height": 1080,
                            "fileUrl": f"https://cdn.example/{video_id}.m3u8?token=secret",
                        }
                    ]
                }
            ]
        }


def _install_fake(monkeypatch):
    monkeypatch.setattr(cli, "_client", lambda args: FakeClient())


def test_list_json_is_normalized_for_agents(monkeypatch, capsys):
    _install_fake(monkeypatch)
    assert cli.main(["list", "live:900001", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["live_id"] == "900001"
    assert data["videos"][0]["video_id"] == "101"
    assert data["videos"][0]["title"] == "First / Talk"


def test_plan_all_with_metadata_template(monkeypatch, capsys, tmp_path):
    _install_fake(monkeypatch)
    rc = cli.main(
        [
            "plan",
            "live:900001",
            "--all",
            "--dir",
            str(tmp_path),
            "--template",
            "{index:02d} - {speaker} - {title} [{video_id}]",
            "--json",
        ]
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True
    assert data["items"][0]["path"].endswith("01 - Alice - First _ Talk [101].mp4")
    assert Path(data["items"][0]["path"]).parent.name == "01 - Alice - First _ Talk [101]"
    assert data["items"][1]["path"].endswith("02 - Bob - Second Talk [102].mp4")
    assert "token=secret" not in data["items"][0]["media_url"]


def test_download_dry_run_exact_path(monkeypatch, capsys, tmp_path):
    _install_fake(monkeypatch)
    target = tmp_path / "chosen-name.mp4"
    rc = cli.main(
        [
            "download",
            "live:900001",
            "--video-id",
            "101",
            "--path",
            str(target),
            "--dry-run",
            "--json",
        ]
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["downloads"][0]["status"] == "dry-run"
    assert Path(data["downloads"][0]["path"]) == target.resolve()


def test_name_rejected_for_multiple_videos(monkeypatch, capsys):
    _install_fake(monkeypatch)
    rc = cli.main(["download", "live:900001", "--all", "--name", "same.mp4", "--dry-run", "--json"])
    assert rc == 2
    err = json.loads(capsys.readouterr().err)
    assert err["ok"] is False
    assert "exactly one" in err["error"]


def test_write_sidecars_uses_final_video_basename(monkeypatch, tmp_path):
    downloaded = []

    def fake_download(url, output, *, timeout):
        downloaded.append((url, output, timeout))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"asset")
        return output

    monkeypatch.setattr(cli, "download_asset", fake_download)
    video_path = tmp_path / "Formatted Talk [700001].mp4"
    row = {
        "path": str(video_path),
        "metadata": {
            "coverUrl": "https://cdn.example/cover.png",
            "blurb": "<p>Abstract</p>",
            "subtitleUrl": "https://cdn.example/subtitles/en.vtt",
        },
        "live_metadata": {},
    }
    args = Namespace(
        write_cover=False,
        write_description=False,
        write_subs=False,
        write_sidecars=True,
        timeout=12,
    )
    result = cli._write_requested_sidecars(row, args)
    assert Path(result["cover"]).name == "Formatted Talk [700001].cover.png"
    assert Path(result["description"]).name == "Formatted Talk [700001].description.html"
    assert Path(result["subtitles"][0]).name == "Formatted Talk [700001].subtitle-1.vtt"
    assert len(downloaded) == 2


def test_generic_replay_title_is_prefixed_with_live_title():
    assert (
        cli._resolved_live_video_title(
            {"id": 700001, "name": "回放2", "isFastBack": True},
            {"title": "Complete Lecture Title"},
            "fallback",
        )
        == "Complete Lecture Title - 回放2"
    )


def test_meaningful_replay_title_is_not_changed():
    assert (
        cli._resolved_live_video_title(
            {"videoId": 700001, "title": "Invited Talk"},
            {"title": "Conference Session"},
            "fallback",
        )
        == "Invited Talk"
    )


def test_download_defaults_enable_subdirectory_and_sidecars():
    args = cli.build_parser().parse_args(["download", "video:700001"])
    assert args.output_dir is None
    assert args.subdir is True
    assert args.write_sidecars is True


def test_download_defaults_can_be_disabled():
    args = cli.build_parser().parse_args(
        ["download", "video:700001", "--no-subdir", "--no-write-sidecars"]
    )
    assert args.subdir is False
    assert args.write_sidecars is False


def test_output_path_supports_nested_and_flat_layouts(tmp_path):
    filename = "Formatted Talk [700001].mp4"
    assert cli._output_path(tmp_path, filename, subdir=True) == (
        tmp_path / "Formatted Talk [700001]" / filename
    )
    assert cli._output_path(tmp_path, filename, subdir=False) == tmp_path / filename
